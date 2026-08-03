"""UCM-15 - Contract of `POST /baseline/compose` and `GET /baseline/{id}/audit-log`.

The composition endpoint is declared here in full — request, response, validation
and OpenAPI — and its body lands in **UCM-16**, which this ticket blocks precisely
so it can be built against a contract that already exists. The route answers 501
after validating the request: the endpoint is real and the surface is closed at
five (invariant 4); what is pending is the logic, not the interface.

Everything below is shaped by what a *sovereign composition* has to be able to
prove afterwards, which is the research question of the TFM:

* **A choice without a written justification is not a choice.** `rationale` is
  non-blank on every entry, exactly as `AuditEventCreate` demands (UCM-11). The
  point of this engine is not that the operator can choose — it is that the choice
  is on the record, with its reason, its actor and its moment.
* **The human's decisions chain onto an engine run.** `run_id` is the one
  `POST /candidates` returned, so the trail reads as one story: what the engine
  decided, what it offered, what the human picked, and what they signed.
* **Tier 0 is verified before signing, not after.** The engine's own reading is
  `ProfilePrioritization.tier_0_complete`; the human closes what is outstanding
  with a mechanism or a justified compensatory control. `ComposedBaseline`
  therefore reports the verification alongside the signature rather than implying
  it.
* **The domain model of the baseline belongs to UCM-16.** What is fixed here is
  the *API* contract — what a client sends and what it can rely on receiving.
  UCM-16 may enrich the response; it may not narrow it.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.assets.schemas import AssetProfile
from app.audit.schemas import AuditEventRead, ChainVerification

# Same rule as the ledger's: a justification is either written or the decision
# does not exist.
NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ChoiceKind(str, Enum):
    """What the operator did about one capability. Mirrors the human event types.

    These are the four decisions of a composition, and they are the same four the
    audit log knows how to file (`HUMAN_EVENT_TYPES`, UCM-11). The fifth human
    event — `baseline_signed` — is not a per-capability choice: it is the act of
    signing the whole thing, and it is carried by `signature` below.
    """

    OPTION_SELECTED = "option_selected"
    OPTION_REJECTED = "option_rejected"
    COMPENSATORY_DECLARED = "compensatory_declared"
    GAP_ACCEPTED = "gap_accepted"


class CompositionChoice(BaseModel):
    """One decision of the operator, with the reason they gave for it."""

    model_config = ConfigDict(extra="forbid")

    kind: ChoiceKind
    zone_id: str = Field(description="Zona en la que se toma la decisión.")
    capability_id: str = Field(description="Capacidad sobre la que se decide.")
    control_id: str | None = Field(
        default=None,
        description=(
            "Control elegido, rechazado o declarado como compensatorio. Se omite — y solo se "
            "omite — al aceptar un hueco, que por definición no tiene mecanismo."
        ),
    )
    rationale: NonBlank = Field(
        description="Justificación escrita por el operador. Queda en la bitácora tal cual."
    )
    # SHA-256 of the explanations the operator had on screen when deciding
    # (`CapabilityExplanations.digest`, UCM-14). Optional, and it never affects the
    # decision: it records *what was being read*, so a P1 layer that decided
    # nothing can still be reconstructed from the log.
    explanations_digest: str | None = None

    @model_validator(mode="after")
    def _a_mechanism_decision_names_its_mechanism(self) -> CompositionChoice:
        if self.kind is ChoiceKind.GAP_ACCEPTED:
            if self.control_id is not None:
                raise ValueError(
                    f"'{self.kind.value}' en {self.capability_id} nombra el control "
                    f"'{self.control_id}': aceptar un hueco es aceptar que no hay mecanismo"
                )
            return self
        if not self.control_id:
            raise ValueError(
                f"'{self.kind.value}' en {self.capability_id} no dice sobre qué control decide"
            )
        return self


class Signature(BaseModel):
    """Who signs the baseline, and why they consider it complete."""

    model_config = ConfigDict(extra="forbid")

    operator: NonBlank = Field(description="Persona que compone y firma. Queda como actor.")
    rationale: NonBlank = Field(
        description="Por qué esta línea base es la adecuada para el activo y sus zonas."
    )


class ComposeRequest(BaseModel):
    """Body of `POST /baseline/compose`: the human's choices over one engine run."""

    model_config = ConfigDict(extra="forbid")

    run_id: UUID = Field(description="Identificador de la ejecución devuelta por POST /candidates.")
    profile: AssetProfile | None = Field(
        default=None, description="Perfil revisado. Excluyente con 'profile_id'."
    )
    profile_id: str | None = Field(
        default=None, description="Identificador de un perfil congelado en el repositorio."
    )
    choices: list[CompositionChoice] = Field(
        min_length=1,
        description="Decisiones del operador, en el orden en que las tomó.",
    )
    signature: Signature


class ComposedCapability(BaseModel):
    """How one capability ended up in the signed baseline."""

    model_config = ConfigDict(extra="forbid")

    zone_id: str
    capability_id: str
    # Never `False`, for the same reason as `CapabilityGating.required`: composing
    # chooses mechanisms, it does not repeal requirements.
    selected_control_ids: list[str] = Field(default_factory=list)
    rejected_control_ids: list[str] = Field(default_factory=list)
    compensatory_control_ids: list[str] = Field(default_factory=list)
    gap_accepted: bool = False
    rationale: str


class ComposedZone(BaseModel):
    """The signed baseline for one zone. Same catalog, different zone, different result."""

    model_config = ConfigDict(extra="forbid")

    zone_id: str
    capabilities: list[ComposedCapability] = Field(default_factory=list)
    tier_0_complete: bool
    outstanding_capability_ids: list[str] = Field(default_factory=list)
    rationale: str


class ComposedBaseline(BaseModel):
    """Response of `POST /baseline/compose`: the signed baseline and its handle.

    `audit_log_path` is not decoration. A signed baseline whose trail the holder
    cannot find is a signature over nothing, so the response points at the endpoint
    that serves it.
    """

    model_config = ConfigDict(extra="forbid")

    baseline_id: UUID
    run_id: UUID
    profile_id: str
    profile_name: str
    signed_by: str
    signed_at: datetime
    # Catalog, precedence, gating and prioritisation versions that governed the run
    # this baseline was composed from: the same signature over a different catalog
    # is a different baseline (invariant 3).
    versions: dict[str, str] = Field(default_factory=dict)
    tier_0_complete: bool
    zones: list[ComposedZone] = Field(default_factory=list)
    audit_events: int = 0
    audit_log_path: str


class BaselineAuditLog(BaseModel):
    """Response of `GET /baseline/{id}/audit-log`: the full trail, and proof of it.

    The events come back as they were written — engine decisions and human ones,
    in ledger order — and `chain` is the re-walk of their hash chain. The log does
    not only *claim* to be append-only: the client gets what it needs to check that
    no field was edited and no entry removed between two events that follow one
    another (`audit/chain.py`).
    """

    model_config = ConfigDict(extra="forbid")

    baseline_id: UUID
    events: list[AuditEventRead] = Field(default_factory=list)
    chain: ChainVerification
    engine_events: int
    human_events: int
    rationale: str
