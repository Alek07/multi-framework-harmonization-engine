"""Output contract of the deterministic core, steps 1-4.

UCM-8 (mapping + conflict resolution), UCM-9 (gating) and UCM-10
(prioritisation) are explicit here: which candidates a capability has per zone,
which conflicts were found, how each one was resolved (and under which declared
rule), which mechanisms the asset profile rules out — and with what
justification — which gaps remain, and in what order what is left should be
built. Nothing is dropped: a candidate that does not prevail is *marked*, never
removed, a mechanism that does not apply is *excluded with a reason*, and a
capability without an effective mechanism becomes an explicit gap (invariant: 0
silent omissions).
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.assets.schemas import SLVector, TechNature
from app.catalog.schemas import (
    Capability,
    Framework,
    FrameworkControl,
    Jurisdiction,
    Mapping,
    MappingType,
)


class ZoneDomain(str, Enum):
    """Zone context that decides framework precedence (IT/OT axis of the catalog)."""

    OT = "OT"
    IT = "IT"
    HYBRID = "HYBRID"


class FoundationalRequirement(str, Enum):
    """The seven IEC 62443 foundational requirements the SL-target is declared over."""

    FR1 = "FR1"
    FR2 = "FR2"
    FR3 = "FR3"
    FR4 = "FR4"
    FR5 = "FR5"
    FR6 = "FR6"
    FR7 = "FR7"


class CandidateStatus(str, Enum):
    """What the deterministic core says about a candidate — it never deletes one."""

    ELIGIBLE = "eligible"
    # Loses a declared contradiction by zone precedence; stays visible and traceable.
    SUPERSEDED = "superseded"
    # Real conflict the engine must not settle: escalated to the human.
    CONTESTED = "contested"


class ConflictType(str, Enum):
    """The three situations of UCM-8."""

    OVERLAP = "overlap"
    GRANULARITY = "granularity"
    CONTRADICTION = "contradiction"


class ResolutionMethod(str, Enum):
    COLLAPSED = "collapsed"
    COVERAGE_WEIGHTS = "coverage_weights"
    FRAMEWORK_PRECEDENCE = "framework_precedence"
    SAFETY_OVERRIDE = "safety_override"


class GapKind(str, Enum):
    """Why a capability is not fully covered in a zone. Never silent."""

    NO_CANDIDATE = "no_candidate"
    NO_EFFECTIVE_MECHANISM = "no_effective_mechanism"
    PARTIAL_ONLY = "partial_only"
    RESIDUAL_COVERAGE = "residual_coverage"


class ZoneContext(BaseModel):
    """Zone reading derived from the `AssetProfile` (deterministic, with its rationale)."""

    model_config = ConfigDict(extra="forbid")

    zone_id: str
    domain: ZoneDomain
    target_sl: int
    safety_relevant: bool
    # Carried verbatim from the zone, and carried *separately* from
    # `safety_relevant` on purpose. The role is what the profile declares
    # ("crown_jewel" for the SIS); safety relevance is a conclusion the engine
    # draws, and it draws it for the whole OT corridor too because the physical
    # consequence is catastrophic. Folding one into the other — which is what
    # v0.1.0 did — left the crown jewel with no premise of its own and made its
    # baseline identical to the corridor's, mechanism for mechanism (UCM-44).
    role: str | None = None
    derivation: str
    # Carried verbatim from the zone: the premises gating reads (UCM-9). They
    # travel *inside* the zone reading rather than beside it so no caller can pair
    # one zone's context with another zone's nature.
    nature: TechNature
    # SL-target per foundational requirement, when the zone declares one. A zone
    # rarely wants the same level everywhere (a corridor may demand SL3 on
    # integrity and SL2 on confidentiality) and Tier 0 is read from it.
    sl_vector: SLVector | None = None

    def sl_target_for(self, requirement: FoundationalRequirement) -> int:
        """The zone's SL-target for one FR — the scalar target when no vector is declared."""
        if self.sl_vector is None:
            return self.target_sl
        return int(getattr(self.sl_vector, requirement.value))


class CandidateOption(BaseModel):
    """A control offered for a capability in a zone, with its status and reason."""

    model_config = ConfigDict(extra="forbid")

    control: FrameworkControl
    mapping: Mapping
    status: CandidateStatus = CandidateStatus.ELIGIBLE
    status_reason: str | None = None
    rule_id: str | None = None

    @property
    def control_id(self) -> str:
        return self.control.id

    @property
    def framework(self) -> Framework:
        return self.control.framework

    @property
    def mapping_type(self) -> MappingType:
        return self.mapping.mapping_type

    @property
    def coverage_weight(self) -> float:
        return self.mapping.coverage_weight


class Conflict(BaseModel):
    """A detected conflict and how it was resolved — or why it goes to the human."""

    model_config = ConfigDict(extra="forbid")

    id: str
    conflict_type: ConflictType
    capability_id: str
    zone_id: str
    control_ids: list[str]
    method: ResolutionMethod
    prevailing_control_ids: list[str] = Field(default_factory=list)
    superseded_control_ids: list[str] = Field(default_factory=list)
    requires_human_decision: bool = False
    rationale: str
    rule_id: str | None = None


class CapabilityGap(BaseModel):
    """Explicit gap: what is missing, how much, and why."""

    model_config = ConfigDict(extra="forbid")

    capability_id: str
    zone_id: str
    kind: GapKind
    coverage: float
    residual: float
    rationale: str


class CapabilityResolution(BaseModel):
    """Everything the core knows about one capability in one zone."""

    model_config = ConfigDict(extra="forbid")

    capability: Capability
    zone_id: str
    options: list[CandidateOption]
    coverage: float
    has_full_mechanism: bool
    conflicts: list[Conflict] = Field(default_factory=list)
    gap: CapabilityGap | None = None

    @property
    def eligible_options(self) -> list[CandidateOption]:
        return [o for o in self.options if o.status is not CandidateStatus.SUPERSEDED]


class ZoneResolution(BaseModel):
    """Resolution of every catalog capability for a single zone."""

    model_config = ConfigDict(extra="forbid")

    zone: ZoneContext
    capabilities: list[CapabilityResolution]

    @property
    def conflicts(self) -> list[Conflict]:
        return [c for cap in self.capabilities for c in cap.conflicts]

    @property
    def gaps(self) -> list[CapabilityGap]:
        return [cap.gap for cap in self.capabilities if cap.gap is not None]

    @property
    def open_decisions(self) -> list[Conflict]:
        """Real conflicts surfaced to the human — the engine must not settle them."""
        return [c for c in self.conflicts if c.requires_human_decision]


class ProfileResolution(BaseModel):
    """Steps 1-2 of the core for a whole asset profile. Input to gating (UCM-9)."""

    model_config = ConfigDict(extra="forbid")

    profile_id: str
    profile_name: str
    catalog_version: str
    rules_version: str
    zones: list[ZoneResolution]

    @property
    def conflicts(self) -> list[Conflict]:
        return [c for z in self.zones for c in z.conflicts]

    @property
    def gaps(self) -> list[CapabilityGap]:
        return [g for z in self.zones for g in z.gaps]

    @property
    def open_decisions(self) -> list[Conflict]:
        return [c for z in self.zones for c in z.open_decisions]

    def zone(self, zone_id: str) -> ZoneResolution:
        for z in self.zones:
            if z.zone.zone_id == zone_id:
                return z
        raise KeyError(f"zone not resolved: {zone_id}")


# --- UCM-9: gating ------------------------------------------------------------


class GatingOutcome(str, Enum):
    """The three — and only three — ways a mechanism can leave the zone's baseline."""

    # Justified exclusion: the control's technical premise does not exist here.
    # A deliverable of the baseline, not a gap.
    NOT_APPLICABLE = "not_applicable"
    # The objective still stands, the asset cannot host the mechanism:
    # a compensatory control is owed.
    OBJECTIVE_WITHOUT_MECHANISM = "objective_without_mechanism"
    # Not a zone-layer mechanism at all: deferred to the organizational layer.
    WRONG_SCOPE = "wrong_scope"


class CapabilityStatus(str, Enum):
    """Where a capability stands *after* gating. It is never "removed"."""

    COVERED_BY_MECHANISM = "covered_by_mechanism"
    COMPENSATORY_REQUIRED = "compensatory_required"
    DEFERRED_TO_ORGANIZATIONAL_LAYER = "deferred_to_organizational_layer"


class GatingDecision(BaseModel):
    """One mechanism ruled out of one capability in one zone, with its evidence."""

    model_config = ConfigDict(extra="forbid")

    zone_id: str
    capability_id: str
    control_id: str
    outcome: GatingOutcome
    rule_id: str
    rationale: str
    # Premises read from the profile/zone that made the rule fire, e.g.
    # "nature.general_purpose_os=false" — the audit trail of the exclusion.
    evidence: list[str] = Field(default_factory=list)
    compensation: str | None = None
    deferred_to: str | None = None
    also_matched_rule_ids: list[str] = Field(default_factory=list)


class CapabilityGating(BaseModel):
    """Gating of one capability in one zone. The requirement itself never drops."""

    model_config = ConfigDict(extra="forbid")

    capability_id: str
    zone_id: str
    # The golden rule, written into the contract: gating removes mechanisms,
    # never required capabilities. This field cannot be False.
    required: Literal[True] = True
    status: CapabilityStatus
    retained_control_ids: list[str] = Field(default_factory=list)
    compensatory_control_ids: list[str] = Field(default_factory=list)
    excluded: list[GatingDecision] = Field(default_factory=list)
    coverage: float
    coverage_before_gating: float
    deferred_to: str | None = None
    gap: CapabilityGap | None = None
    rationale: str


class ZoneGating(BaseModel):
    """Gating of every catalog capability for a single zone."""

    model_config = ConfigDict(extra="forbid")

    zone: ZoneContext
    capabilities: list[CapabilityGating]

    @property
    def decisions(self) -> list[GatingDecision]:
        return [d for cap in self.capabilities for d in cap.excluded]

    @property
    def justified_exclusions(self) -> list[GatingDecision]:
        """*No aplica*: a deliverable of the baseline — what was left out and why."""
        return [d for d in self.decisions if d.outcome is GatingOutcome.NOT_APPLICABLE]

    @property
    def compensatory_requirements(self) -> list[GatingDecision]:
        """*Objetivo sin mecanismo*: what the human owes a compensatory control for."""
        return [d for d in self.decisions if d.outcome is GatingOutcome.OBJECTIVE_WITHOUT_MECHANISM]

    @property
    def organizational_deferrals(self) -> list[GatingDecision]:
        """*Ámbito equivocado*: what leaves the asset layer without leaving the register."""
        return [d for d in self.decisions if d.outcome is GatingOutcome.WRONG_SCOPE]

    @property
    def gaps(self) -> list[CapabilityGap]:
        return [cap.gap for cap in self.capabilities if cap.gap is not None]

    def capability(self, capability_id: str) -> CapabilityGating:
        for cap in self.capabilities:
            if cap.capability_id == capability_id:
                return cap
        raise KeyError(f"capability not gated: {capability_id}")


class ProfileGating(BaseModel):
    """Step 3 of the core for a whole asset profile. Input to prioritisation (UCM-10)."""

    model_config = ConfigDict(extra="forbid")

    profile_id: str
    profile_name: str
    catalog_version: str
    rules_version: str
    gating_version: str
    zones: list[ZoneGating]

    @property
    def decisions(self) -> list[GatingDecision]:
        return [d for z in self.zones for d in z.decisions]

    @property
    def justified_exclusions(self) -> list[GatingDecision]:
        return [d for z in self.zones for d in z.justified_exclusions]

    @property
    def compensatory_requirements(self) -> list[GatingDecision]:
        return [d for z in self.zones for d in z.compensatory_requirements]

    @property
    def organizational_deferrals(self) -> list[GatingDecision]:
        return [d for z in self.zones for d in z.organizational_deferrals]

    @property
    def gaps(self) -> list[CapabilityGap]:
        return [g for z in self.zones for g in z.gaps]

    def zone(self, zone_id: str) -> ZoneGating:
        for z in self.zones:
            if z.zone.zone_id == zone_id:
                return z
        raise KeyError(f"zone not gated: {zone_id}")


# --- UCM-10: prioritisation ---------------------------------------------------


class PriorityTier(str, Enum):
    """The two tiers of the ticket. They are never ranked against each other."""

    # Mandatory at the zone's SL-target (or by legal obligation): not prioritised.
    TIER_0 = "tier_0"
    # Discretionary: this is the only thing the engine orders.
    TIER_1 = "tier_1"


class MandateSource(str, Enum):
    """Why a capability is mandatory. Both sources are read from declared data."""

    SL_TARGET = "sl_target"
    LEGAL_OBLIGATION = "legal_obligation"


class OrdinalLevel(str, Enum):
    """The only scale the prioritisation uses. Comparable, never addable."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ImplementationLayer(str, Enum):
    """Where the work is carried out — gating decides this, prioritisation reports it."""

    ASSET = "asset"
    ORGANIZATIONAL = "organizational"


class Mandate(BaseModel):
    """One reason a capability is Tier 0, with the evidence that supports it."""

    model_config = ConfigDict(extra="forbid")

    source: MandateSource
    control_id: str
    official_id: str
    framework: Framework
    jurisdiction: Jurisdiction
    foundational_requirement: FoundationalRequirement | None = None
    required_at_sl: int | None = None
    zone_sl_target: int | None = None
    rationale: str


class CapabilityPriority(BaseModel):
    """Where one capability sits in the roadmap of one zone, and why."""

    model_config = ConfigDict(extra="forbid")

    capability_id: str
    zone_id: str
    tier: PriorityTier
    layer: ImplementationLayer
    status: CapabilityStatus
    mandates: list[Mandate] = Field(default_factory=list)
    coverage: float
    coverage_level: OrdinalLevel
    # Capabilities this one enables (declared dependants) and its prerequisites.
    leverage: int
    unlocks: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    benefit: OrdinalLevel
    cost: OrdinalLevel
    # Null on Tier 0 — and that is the contract, not a missing value: what is
    # mandatory at the zone's SL-target is not ranked, it is completed.
    priority: OrdinalLevel | None = None
    # CIS Implementation Group of the retained CIS mechanism, when there is one.
    implementation_group: str | None = None
    phase: int
    # Tier 0 that gating left without an applicable mechanism, or with a declared
    # residual: what the human must close before the baseline can be signed.
    outstanding: bool = False
    gap: CapabilityGap | None = None
    rationale: str


class RoadmapPhase(BaseModel):
    """A phase of the roadmap. Phase 0 is the mandatory block and is not a ranking."""

    model_config = ConfigDict(extra="forbid")

    index: int
    name: str
    tier: PriorityTier
    capability_ids: list[str] = Field(default_factory=list)
    rationale: str


class ZonePrioritization(BaseModel):
    """Step 4 of the core for a single zone: tiers, ordinal order and phased roadmap."""

    model_config = ConfigDict(extra="forbid")

    zone: ZoneContext
    capabilities: list[CapabilityPriority]
    phases: list[RoadmapPhase]

    @property
    def tier_0(self) -> list[CapabilityPriority]:
        return [c for c in self.capabilities if c.tier is PriorityTier.TIER_0]

    @property
    def tier_1(self) -> list[CapabilityPriority]:
        return [c for c in self.capabilities if c.tier is PriorityTier.TIER_1]

    @property
    def outstanding_mandates(self) -> list[CapabilityPriority]:
        """Mandatory capabilities not yet complete — the pre-signature checklist."""
        return [c for c in self.capabilities if c.outstanding]

    @property
    def tier_0_complete(self) -> bool:
        return not self.outstanding_mandates

    def capability(self, capability_id: str) -> CapabilityPriority:
        for capability in self.capabilities:
            if capability.capability_id == capability_id:
                return capability
        raise KeyError(f"capability not prioritised: {capability_id}")

    def phase(self, index: int) -> RoadmapPhase:
        for phase in self.phases:
            if phase.index == index:
                return phase
        raise KeyError(f"phase not in the roadmap: {index}")


class ProfilePrioritization(BaseModel):
    """Step 4 of the core for a whole asset profile: the phased roadmap per zone."""

    model_config = ConfigDict(extra="forbid")

    profile_id: str
    profile_name: str
    catalog_version: str
    rules_version: str
    gating_version: str
    prioritization_version: str
    zones: list[ZonePrioritization]

    @property
    def outstanding_mandates(self) -> list[CapabilityPriority]:
        return [c for z in self.zones for c in z.outstanding_mandates]

    @property
    def tier_0_complete(self) -> bool:
        """The engine's reading before the human composes (UCM-16).

        False does not mean "cannot be signed": it means the engine cannot claim
        the mandatory block is met on its own, and `outstanding_mandates` is the
        list the human has to close — with a mechanism or with a justified
        compensatory control — for `POST /baseline/compose` to accept the signature.
        """
        return all(z.tier_0_complete for z in self.zones)

    def zone(self, zone_id: str) -> ZonePrioritization:
        for z in self.zones:
            if z.zone.zone_id == zone_id:
                return z
        raise KeyError(f"zone not prioritised: {zone_id}")
