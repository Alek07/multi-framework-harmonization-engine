"""UCM-7 - AssetProfile: the engine's input contract (asset profile).

It is the structured output of the LLM parse (reviewed by the operator) and the
input to gating and prioritization. Pure Pydantic; not persisted as a table
(composed in memory per request).
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


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


class Zone(BaseModel):
    """Security zone (IEC 62443) with its target SL."""

    model_config = ConfigDict(extra="forbid")

    id: str
    target_sl: int = Field(ge=1, le=4)
    purdue: str | None = None
    role: str | None = None
    position: str | None = None
    sl_vector: SLVector | None = None
    safety_out_of_scope: bool = False
    reference: str | None = None


class TechNature(BaseModel):
    """Asset technological nature -> feeds gating."""

    model_config = ConfigDict(extra="forbid")

    general_purpose_os: bool
    networked: bool
    hybrid_it_ot: bool
    interactive_users: bool
    office_it_surface: bool


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
    """Asset profile: identification, zones, nature, conduits, criticality."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    case: CaseType
    zones: list[Zone]
    nature: TechNature
    conduits: list[Conduit]
    criticality: Criticality
