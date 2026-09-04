from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Annotated, Any
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.core.schemas import ORMBase

# A justification is either written or the event does not exist.
NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class AuditActor(str, Enum):
    """Who decided. Only two actors exist in this system — and the AI is neither."""

    ENGINE = "engine"
    HUMAN = "human"


class AuditStage(str, Enum):
    """Which step of the pipeline the decision belongs to."""

    # Lifecycle of one run of the deterministic core.
    RUN = "run"
    MAPPING = "mapping"
    CONFLICT_RESOLUTION = "conflict_resolution"
    GATING = "gating"
    PRIORITIZATION = "prioritization"
    # The RAG pass. It decides nothing — it only adds options — but it is logged
    # for the invariant it must satisfy: coverage is only ever widened, and a
    # declared lens that sets a candidate aside says so on the record.
    RETRIEVAL = "retrieval"
    # Where the human takes over.
    COMPOSITION = "composition"
    SIGNATURE = "signature"


class AuditEventType(str, Enum):
    """What happened. Each type belongs to exactly one actor (see `actor_for`)."""

    # --- engine (deterministic core) ---
    RUN_STARTED = "run_started"
    ZONE_DERIVED = "zone_derived"
    CAPABILITY_MAPPED = "capability_mapped"
    CONFLICT_RESOLVED = "conflict_resolved"
    CONFLICT_ESCALATED = "conflict_escalated"
    GAP_DECLARED = "gap_declared"
    MECHANISM_EXCLUDED = "mechanism_excluded"
    CAPABILITY_STATUS_SET = "capability_status_set"
    MANDATE_RECORDED = "mandate_recorded"
    MANDATE_OUTSTANDING = "mandate_outstanding"
    PRIORITY_ASSIGNED = "priority_assigned"
    ROADMAP_PHASED = "roadmap_phased"
    STAGE_COMPLETED = "stage_completed"
    RUN_COMPLETED = "run_completed"

    # --- engine (RAG pass) ---
    # Candidates offered on top of the catalog's, for one capability in one zone.
    CANDIDATES_RETRIEVED = "candidates_retrieved"
    CANDIDATE_SET_ASIDE = "candidate_set_aside"
    CANDIDATES_CUT = "candidates_cut"

    # --- human (sovereign composition) ---
    OPTION_SELECTED = "option_selected"
    OPTION_REJECTED = "option_rejected"
    COMPENSATORY_DECLARED = "compensatory_declared"
    GAP_ACCEPTED = "gap_accepted"
    MECHANISM_RATIFIED = "mechanism_ratified"
    BASELINE_SIGNED = "baseline_signed"


HUMAN_EVENT_TYPES = frozenset(
    {
        AuditEventType.OPTION_SELECTED,
        AuditEventType.OPTION_REJECTED,
        AuditEventType.COMPENSATORY_DECLARED,
        AuditEventType.GAP_ACCEPTED,
        AuditEventType.MECHANISM_RATIFIED,
        AuditEventType.BASELINE_SIGNED,
    }
)


def actor_for(event_type: AuditEventType) -> AuditActor:
    """The only actor allowed to author this kind of event.

    Composition and signature belong to the human; everything the deterministic
    core does belongs to the engine. Nothing in between, and nothing anonymous.
    """
    return AuditActor.HUMAN if event_type in HUMAN_EVENT_TYPES else AuditActor.ENGINE


def as_utc(value: datetime) -> datetime:
    """Normalise a timestamp to aware UTC.

    SQLite does not keep the offset, so a timestamp written as aware UTC comes
    back naive. Reading it as UTC is what makes the chain digest reproducible
    across write and read (`chain.event_digest`).
    """
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class AuditEventCreate(BaseModel):
    """One entry to append. The ledger — not the caller — supplies order and time."""

    model_config = ConfigDict(extra="forbid")

    actor: AuditActor
    # Which engine component (`engine.gating`) or which operator signed it.
    actor_ref: str | None = None
    stage: AuditStage
    event_type: AuditEventType
    run_id: UUID
    baseline_id: UUID | None = None
    profile_id: str
    zone_id: str | None = None
    capability_id: str | None = None
    control_id: str | None = None
    rule_id: str | None = None
    decision: NonBlank
    rationale: NonBlank
    versions: dict[str, str] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _actor_matches_event_type(self) -> AuditEventCreate:
        expected = actor_for(self.event_type)
        if self.actor is not expected:
            raise ValueError(
                f"'{self.event_type.value}' is authored by '{expected.value}', "
                f"not by '{self.actor.value}'"
            )
        return self


class AuditEventRead(ORMBase):
    """A persisted entry, with its position in the chain and its digest."""

    id: UUID
    sequence: int
    recorded_at: datetime
    actor: AuditActor
    actor_ref: str | None
    stage: AuditStage
    event_type: AuditEventType
    run_id: UUID
    baseline_id: UUID | None
    profile_id: str
    zone_id: str | None
    capability_id: str | None
    control_id: str | None
    rule_id: str | None
    decision: str
    rationale: str
    versions: dict[str, str]
    payload: dict[str, Any]
    prev_hash: str
    event_hash: str

    @field_validator("recorded_at")
    @classmethod
    def _utc(cls, value: datetime) -> datetime:
        return as_utc(value)


class ChainVerification(BaseModel):
    """Result of re-walking the chain: whether the log can still be trusted."""

    model_config = ConfigDict(extra="forbid")

    valid: bool
    events: int
    first_broken_sequence: int | None = None
    detail: str
