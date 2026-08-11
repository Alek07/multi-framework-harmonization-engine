"""UCM-15/UCM-16 - Contract of `POST /baseline/compose`, the baseline's trail and the list of them.

The request shape was fixed in UCM-15, before the logic existed, so the endpoint
could be built against a contract rather than the other way round. UCM-16 fills
that contract in and *enriches the response*; it changes nothing a client sends.

Everything here is shaped by what a *sovereign composition* has to be able to
prove afterwards, which is the research question of the TFM:

* **A choice without a written justification is not a choice.** `rationale` is
  non-blank on every entry, exactly as `AuditEventCreate` demands (UCM-11). The
  point of this engine is not that the operator can choose — it is that the choice
  is on the record, with its reason, its actor and its moment.
* **The human's decisions chain onto an engine run.** `run_id` is the one
  `POST /candidates` returned, so the trail reads as one story: what the engine
  decided, what it offered, what the human picked, and what they signed.
* **Tier 0 is verified before signing, not after.** The engine's outstanding
  mandates are what the human must close — with a mechanism, a compensatory
  control or a written acceptance — and a signature is *refused* while any of them
  is open. Everything else in Tier 0 is **ratified** by the signature and recorded
  as such, which is a different sentence from "the operator chose it".
* **Nothing about the baseline is implicit.** Every mandatory capability of every
  zone leaves a human-authored entry in the ledger: chosen, compensated, accepted
  as a gap, or ratified. There is no path where a mandatory mechanism ends up in a
  signed baseline with nobody's name on it.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.assets.schemas import AssetProfile
from app.audit.schemas import AuditEventRead, ChainVerification
from app.core.wording import say
from app.engine.schemas import CapabilityStatus, PriorityTier

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
                    f"La {say(self.kind)} en {self.capability_id} nombra el control "
                    f"'{self.control_id}': aceptar un hueco es aceptar que no hay mecanismo"
                )
            return self
        if not self.control_id:
            raise ValueError(
                f"La {say(self.kind)} en {self.capability_id} no dice sobre qué control decide"
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

    run_id: UUID = Field(
        description="Identificador de la ejecución del motor de la que salieron las opciones."
    )
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


class SelectionOrigin(str, Enum):
    """Where a chosen control came from. Provenance, never a quality order.

    A crosswalk translates; this engine advises the selection — so it matters, and
    it is recorded, whether the operator picked a mechanism the catalog *already
    maps* to the capability or adopted one that only the RAG pass had suggested.
    The second is a human judgement on top of the catalog, and calling it anything
    else would let an embedding distance pass for an authored mapping.
    """

    CATALOG_MAPPING = "catalog_mapping"
    ADOPTED_SUGGESTION = "adopted_suggestion"


class ComposedCapability(BaseModel):
    """How one capability ended up in the signed baseline, and who put it there."""

    model_config = ConfigDict(extra="forbid")

    zone_id: str
    capability_id: str
    capability_name: str
    tier: PriorityTier
    # Gating's reading of the capability *before* the human composed on top of it.
    status: CapabilityStatus
    # The engine could not close this mandate on its own: no applicable mechanism
    # left, or a declared residual. It is what the human had to decide about.
    outstanding: bool = False
    # Never `False`, for the same reason as `CapabilityGating.required`: composing
    # chooses mechanisms, it does not repeal requirements.
    required: bool = True
    selected_control_ids: list[str] = Field(default_factory=list)
    rejected_control_ids: list[str] = Field(default_factory=list)
    compensatory_control_ids: list[str] = Field(default_factory=list)
    # Chosen mechanisms the catalog does *not* map to this capability: the operator
    # adopted a suggestion, and the baseline says so rather than absorbing it.
    adopted_control_ids: list[str] = Field(default_factory=list)
    # Mechanisms the deterministic core had retained and the signature accepted
    # without a choice among equivalents. Empty whenever the operator decided
    # explicitly — the two are recorded as different acts.
    ratified_control_ids: list[str] = Field(default_factory=list)
    gap_accepted: bool = False
    rationale: str

    @property
    def decided_by_human(self) -> bool:
        return bool(
            self.selected_control_ids
            or self.compensatory_control_ids
            or self.gap_accepted
        )


class ComposedZone(BaseModel):
    """The signed baseline for one zone. Same catalog, different zone, different result."""

    model_config = ConfigDict(extra="forbid")

    zone_id: str
    capabilities: list[ComposedCapability] = Field(default_factory=list)
    tier_0_complete: bool
    # The mandates the engine could not close on its own and the human closed here.
    # Not "what is still open": a signature is refused while any of them is.
    outstanding_capability_ids: list[str] = Field(default_factory=list)
    rationale: str

    def capability(self, capability_id: str) -> ComposedCapability:
        for capability in self.capabilities:
            if capability.capability_id == capability_id:
                return capability
        raise KeyError(f"capability not composed in {self.zone_id}: {capability_id}")


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
    # Always true on a signed baseline, and that is the contract rather than a
    # computed field that might be false: the signature is refused while any
    # mandate of any zone is open, so a `ComposedBaseline` that exists is one whose
    # mandatory block was verified complete before it was signed.
    tier_0_complete: bool
    zones: list[ComposedZone] = Field(default_factory=list)
    # How many entries the composition appended: one per human decision, one per
    # ratified mandate, and the signature itself.
    audit_events: int = 0
    audit_log_path: str

    def zone(self, zone_id: str) -> ComposedZone:
        for zone in self.zones:
            if zone.zone_id == zone_id:
                return zone
        raise KeyError(f"zone not composed: {zone_id}")


class BaselineSummary(BaseModel):
    """One signed baseline, as the list of them shows it.

    Every field is read from the `baseline_signed` entry the composition appended —
    nothing here is recomputed and nothing is stored twice. That is what makes the
    list trustworthy rather than merely convenient: it cannot drift from the trail,
    because it *is* the trail, read at one remove.

    It is deliberately a summary and not a `ComposedBaseline`. Reconstructing the
    full composition would mean re-running the core over a profile that may no
    longer exist under those versions; what a list needs is who signed what, when,
    and how much was decided by hand — and for the rest there is the trail, which
    `audit_log_path` points at.
    """

    model_config = ConfigDict(extra="forbid")

    baseline_id: UUID
    run_id: UUID
    profile_id: str
    profile_name: str
    signed_by: str
    signed_at: datetime
    versions: dict[str, str] = Field(default_factory=dict)
    zone_ids: list[str] = Field(default_factory=list)
    tier_0_complete: bool
    # Per zone, the mandates the engine could not close on its own and the human
    # therefore had to close by hand before signing. Empty is the ordinary case.
    closed_mandates: dict[str, list[str]] = Field(default_factory=dict)
    # What the operator did, in the four kinds the ledger files. `human_choices`
    # and `ratified_mandates` come from the signature's own payload; the other two
    # are counted over the entries stamped with this baseline.
    human_choices: int = 0
    ratified_mandates: int = 0
    gaps_accepted: int = 0
    conflicts_resolved: int = 0
    audit_events: int = 0
    audit_log_path: str
    # The operator's own justification, as recorded. Not a rendering of it: what
    # a reviewer has to be able to read is the sentence that was signed.
    signature_rationale: str


class BaselineList(BaseModel):
    """Response of `GET /baselines`: every signature the ledger holds, newest first.

    Newest first because the question a list answers is "what has been signed", and
    the answer is read from the top. The order is the ledger's own (`sequence`
    descending) rather than a timestamp comparison — two baselines signed in the
    same second still have an order, and it is the order they were written in.
    """

    model_config = ConfigDict(extra="forbid")

    baselines: list[BaselineSummary] = Field(default_factory=list)
    total: int
    rationale: str


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
