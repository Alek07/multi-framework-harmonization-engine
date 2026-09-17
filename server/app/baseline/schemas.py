"""Contracts of the baseline: composing it, its trail, the list, the declaration.

Shaped by what a sovereign composition has to prove afterwards:

* Every entry carries a non-blank `rationale` — a choice without a written
  justification is not a choice.
* `run_id` chains the human's decisions onto the engine run the candidates came
  from, so the trail reads as one story.
* Tier 0 is verified before signing, never after; what the signature does not
  choose it ratifies, recorded as a distinct act.
* Every mandatory capability leaves a human-authored entry — nothing ends up in
  a signed baseline with nobody's name on it.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Literal
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

    The four per-capability decisions the audit log can file (`HUMAN_EVENT_TYPES`).
    The fifth human event, `baseline_signed`, is not a per-capability choice — it
    is carried by `signature` below.
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
    # SHA-256 of the explanations on screen when deciding
    # (`CapabilityExplanations.digest`). Never affects the decision: it records
    # *what was being read*, so a P1 layer that decided nothing is reconstructable.
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

    Whether the operator picked a mechanism the catalog *already maps* to the
    capability or adopted one only the RAG pass suggested is recorded, because the
    second is a human judgement on top of the catalog: calling it anything else
    would let an embedding distance pass for an authored mapping.
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
    """One signed baseline as the list shows it: its signature entry, read back.

    A summary and not a `ComposedBaseline` — rebuilding one would mean re-running
    the core under versions that may have moved. For the detail there is the trail.
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
    # Per zone, the mandates the engine could not close and the human closed by hand.
    closed_mandates: dict[str, list[str]] = Field(default_factory=dict)
    human_choices: int = 0
    ratified_mandates: int = 0
    gaps_accepted: int = 0
    conflicts_resolved: int = 0
    audit_events: int = 0
    audit_log_path: str
    # The operator's own justification, as recorded — not a rendering of it.
    signature_rationale: str


class BaselineList(BaseModel):
    """Response of `GET /baselines`, newest first.

    Ordered by `sequence` and not by timestamp: two signatures in the same second
    still have an order, and it is the one they were written in.
    """

    model_config = ConfigDict(extra="forbid")

    baselines: list[BaselineSummary] = Field(default_factory=list)
    total: int
    rationale: str


class MechanismDisposition(str, Enum):
    """What became of one mechanism for one capability in one zone.

    Three of these are gating's own outcomes and keep its identifiers on purpose:
    an exclusion here *is* the gating decision that produced it, and renaming it
    would create a second vocabulary for one fact.
    """

    # In the baseline, on the human's word.
    SELECTED = "selected"
    RATIFIED = "ratified"
    COMPENSATORY = "compensatory"
    # On the table and not taken. Kept because a declaration that lists only what
    # was chosen cannot show that there was anything to choose between.
    OFFERED = "offered"
    REJECTED = "rejected"
    # Ruled out by the zone's gating, with rule and premise.
    NOT_APPLICABLE = "not_applicable"
    OBJECTIVE_WITHOUT_MECHANISM = "objective_without_mechanism"
    WRONG_SCOPE = "wrong_scope"


# The three that put a mechanism *in* the signed baseline. Everything else is
# either an offer nobody took or an exclusion with a written reason.
INCLUDED_DISPOSITIONS = frozenset(
    {
        MechanismDisposition.SELECTED,
        MechanismDisposition.RATIFIED,
        MechanismDisposition.COMPENSATORY,
    }
)


class CapabilityOutcome(str, Enum):
    """How one required capability ends up satisfied — or explicitly not.

    There is no `excluded` member and that is the point: gating removes mechanisms,
    never required capabilities, so no value here can say a capability does not
    apply. What varies is *how* it is met, and every way of not meeting it carries
    someone's written reason.
    """

    IMPLEMENTED = "implemented"
    COMPENSATED = "compensated"
    DEFERRED = "deferred"
    ACCEPTED_GAP = "accepted_gap"
    OPEN_GAP = "open_gap"
    # Discretionary, in the roadmap, outside this signature: Tier 1 the operator
    # did not decide about is not part of what they signed (`service._zone`).
    ROADMAP = "roadmap"


class StatementFormat(str, Enum):
    """Which document `GET /baseline/{id}/statement` is asked for."""

    SOA = "soa"
    OSCAL = "oscal"


class StatementMandate(BaseModel):
    """Why a capability is mandatory, as the ledger recorded it.

    Deliberately permissive — every field but `source` optional, unknown keys
    ignored — for the same reason `listing.py` reads payloads with `.get`: an
    entry written before a field existed cannot be migrated, and an old baseline
    should give a poorer document rather than a 500.
    """

    model_config = ConfigDict(extra="ignore")

    source: str
    control_id: str | None = None
    official_id: str | None = None
    framework: str | None = None
    jurisdiction: str | None = None
    foundational_requirement: str | None = None
    required_at_sl: int | None = None
    zone_sl_target: int | None = None
    rationale: str = ""


class StatementGap(BaseModel):
    """The gap a capability carries into the baseline: how much, and why."""

    model_config = ConfigDict(extra="ignore")

    kind: str
    coverage: float | None = None
    residual: float | None = None
    rationale: str = ""


class StatementMechanism(BaseModel):
    """One mechanism under one capability, and what was decided about it.

    This is the row an ISO/IEC 27001 SoA would call a control. Here it is the
    *sub*-unit — the unit is the capability — because a mechanism is the only
    thing that can be excluded.
    """

    model_config = ConfigDict(extra="forbid")

    control_id: str
    official_id: str | None = None
    framework: str | None = None
    jurisdiction: str | None = None
    # The Spanish phrase for the control's declared demand (`ControlStrength.label`).
    strength: str | None = None
    mapping_type: str | None = None
    coverage_weight: float | None = None
    provenance: str | None = None
    disposition: MechanismDisposition
    included: bool
    # Chosen although the catalog does not map it to this capability: the operator
    # adopted a retrieval suggestion. Recorded as adoption and never as mapping.
    adopted: bool = False
    # The gating outcome the operator decided over. Sovereignty includes
    # contradicting the engine; it does not include doing it silently.
    despite_gating: str | None = None
    rule_id: str | None = None
    evidence: list[str] = Field(default_factory=list)
    compensation: str | None = None
    deferred_to: str | None = None
    rationale: str = ""
    audit_sequences: list[int] = Field(default_factory=list)


class StatementRow(BaseModel):
    """One required capability in one zone: the row a reviewer reads."""

    model_config = ConfigDict(extra="forbid")

    zone_id: str
    capability_id: str
    capability_name: str
    # Never `False`, exactly as in `CapabilityGating`: this document reports the
    # composition, and composing chooses mechanisms rather than repealing
    # requirements.
    required: Literal[True] = True
    tier: PriorityTier
    phase: int | None = None
    priority: str | None = None
    layer: str | None = None
    status: CapabilityStatus | None = None
    outcome: CapabilityOutcome
    # Part of what was signed: all of Tier 0, plus the Tier 1 the operator
    # decided about. The rest is reported as roadmap and marked as not signed.
    in_signed_baseline: bool
    outstanding: bool = False
    coverage: float | None = None
    mandates: list[StatementMandate] = Field(default_factory=list)
    jurisdictions: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    mechanisms: list[StatementMechanism] = Field(default_factory=list)
    gap: StatementGap | None = None
    gap_accepted: bool = False
    decided_by_human: bool = False
    # The two justifications are kept apart on purpose. Merging them would let the
    # engine's prose pass for the operator's, and it is the operator's that makes
    # an inclusion or an exclusion admissible.
    human_rationale: str | None = None
    engine_rationale: str = ""
    audit_sequences: list[int] = Field(default_factory=list)


class StatementCounts(BaseModel):
    """The tallies a reviewer checks the document against."""

    model_config = ConfigDict(extra="forbid")

    capabilities: int = 0
    tier_0: int = 0
    tier_1: int = 0
    signed: int = 0
    implemented: int = 0
    compensated: int = 0
    deferred: int = 0
    accepted_gaps: int = 0
    open_gaps: int = 0
    roadmap: int = 0
    included_mechanisms: int = 0
    offered_not_taken: int = 0
    rejected_mechanisms: int = 0
    # The three gating outcomes, which are three different deliverables: a
    # justified exclusion is one, an owed compensatory control is another, and a
    # requirement that changed layer is a third.
    justified_exclusions: int = 0
    compensatory_requirements: int = 0
    organizational_deferrals: int = 0


class StatementZone(BaseModel):
    """The declaration for one zone. Same catalog, different zone, different document."""

    model_config = ConfigDict(extra="forbid")

    zone_id: str
    domain: str | None = None
    target_sl: int | None = None
    safety_relevant: bool | None = None
    role: str | None = None
    tier_0_complete: bool
    rows: list[StatementRow] = Field(default_factory=list)
    counts: StatementCounts
    rationale: str


class BaselineStatement(BaseModel):
    """Response of `GET /baseline/{id}/statement`: the baseline as a declaration.

    Projected from the ledger and from nothing else, so the document cannot say
    anything the trail does not — and so it reports the catalog and rules that
    governed the signature rather than whichever ones are installed today.
    """

    model_config = ConfigDict(extra="forbid")

    baseline_id: UUID
    run_id: UUID
    profile_id: str
    profile_name: str
    signed_by: str
    signed_at: datetime
    signature_rationale: str
    versions: dict[str, str] = Field(default_factory=dict)
    tier_0_complete: bool
    zones: list[StatementZone] = Field(default_factory=list)
    counts: StatementCounts
    # The document carries its own integrity proof: a declaration read off a
    # ledger nobody can verify is a declaration of trust in the ledger.
    chain: ChainVerification
    audit_log_path: str
    rationale: str
    # What this document is *not*. Declared in the artefact itself so it cannot
    # be cited as something it does not claim to be.
    limitations: list[str] = Field(default_factory=list)


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
