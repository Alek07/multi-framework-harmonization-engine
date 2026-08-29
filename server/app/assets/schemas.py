"""UCM-7 - AssetProfile: the engine's input contract (asset profile).

It is the structured output of the LLM parse (reviewed by the operator) and the
input to gating and prioritization. Pure Pydantic; not persisted as a table
(composed in memory per request).
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.catalog.schemas import Sector


class CaseType(str, Enum):
    PURE_OT = "PURE_OT"
    HYBRID_IT_OT = "HYBRID_IT_OT"


class ConsequenceScale(str, Enum):
    CATASTROPHIC = "catastrophic"
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"


class SLVector(BaseModel):
    """SL-T vector per IEC 62443 Foundational Requirement (FR1-FR7), 1-4."""

    model_config = ConfigDict(extra="forbid")

    FR1: int = Field(ge=1, le=4)
    FR2: int = Field(ge=1, le=4)
    FR3: int = Field(ge=1, le=4)
    FR4: int = Field(ge=1, le=4)
    FR5: int = Field(ge=1, le=4)
    FR6: int = Field(ge=1, le=4)
    FR7: int = Field(ge=1, le=4)


class TechNature(BaseModel):
    """Technological nature of what a zone contains -> feeds gating.

    Declared per zone, not per asset. A hybrid asset holds zones of different
    natures at once — an embedded safety controller on the jetty and a Windows
    operator station in the control room — and a single asset-wide reading has to
    be wrong about one of them: `general_purpose_os=true` suppresses the
    *no-aplica* exclusion the controller is owed, `false` gates the workstation as
    if it ran firmware. Gating reads these premises per zone (UCM-9), so this is
    where they belong.
    """

    model_config = ConfigDict(extra="forbid")

    general_purpose_os: bool
    networked: bool
    hybrid_it_ot: bool
    interactive_users: bool
    office_it_surface: bool


class Zone(BaseModel):
    """Security zone (IEC 62443) with its target SL and its technological nature."""

    model_config = ConfigDict(extra="forbid")

    id: str
    target_sl: int = Field(ge=1, le=4)
    nature: TechNature
    purdue: str | None = None
    role: str | None = None
    position: str | None = None
    sl_vector: SLVector | None = None
    safety_out_of_scope: bool = False
    reference: str | None = None
    # The sectors this zone operates in (UCM-47), overriding the asset's when they
    # differ — the same reason `nature` lives on the zone. A gas corridor with a
    # maritime berth zone is one asset in two sectors at once, and an asset-wide
    # reading would have to be wrong about one of them: it would either offer IMO
    # to the whole corridor or withhold it from the berth. Empty = inherit the
    # asset's sectors, which is the common case.
    sectors: list[Sector] = Field(default_factory=list)


class Conduit(BaseModel):
    """Conduit between zones (incl. IDMZ)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    endpoints: list[str]
    control: str


class Criticality(BaseModel):
    """Asset physical consequence -> weighs in prioritization."""

    model_config = ConfigDict(extra="forbid")

    physical_consequence: str
    scale: ConsequenceScale
    threat_model: str
    consequence_path: str | None = None
    attack_reference: str | None = None


class AssetProfile(BaseModel):
    """Asset profile: identification, zones, conduits, criticality.

    The technological nature lives on each `Zone`, not here: see `TechNature`.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    case: CaseType
    # The sectors the asset operates in (UCM-47), the premise sectoral
    # applicability reads. A list: a port is transport and energy at once, and a
    # zone may narrow it (`Zone.sectors`). Empty by default — an asset that
    # declares no sector cannot have a norm asserted out of scope, so an empty
    # list excludes nothing and every candidate is offered, the safe reading a
    # wrong exclusion would betray (invariant 2). The parse fills it in, empty
    # when the text does not say, and the operator completes it.
    sectors: list[Sector] = Field(default_factory=list)
    zones: list[Zone]
    conduits: list[Conduit]
    criticality: Criticality
