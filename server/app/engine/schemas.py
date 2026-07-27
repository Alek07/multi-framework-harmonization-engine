"""UCM-8 - Output contract of core steps 1-2 (mapping + conflict resolution).

Everything the engine decides is explicit here: which candidates a capability
has per zone, which conflicts were found, how each one was resolved (and under
which declared rule), and which gaps remain. Nothing is dropped: a candidate
that does not prevail is *marked*, never removed, and a capability without an
effective mechanism becomes an explicit gap (invariant: 0 silent omissions).
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.catalog.schemas import Capability, Framework, FrameworkControl, Mapping, MappingType


class ZoneDomain(str, Enum):
    """Zone context that decides framework precedence (IT/OT axis of the catalog)."""

    OT = "OT"
    IT = "IT"
    HYBRID = "HYBRID"


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
    derivation: str


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
