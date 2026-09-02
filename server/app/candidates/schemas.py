from __future__ import annotations

from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.assets.schemas import AssetProfile
from app.engine.schemas import (
    CapabilityGating,
    CapabilityPriority,
    CapabilityResolution,
    Conflict,
    RoadmapPhase,
    ZoneContext,
)
from app.explain.schemas import CapabilityExplanations
from app.retrieval.schemas import (
    CapabilityRetrieval,
    PayloadFilter,
    RetrievalProvenance,
)


class ExplainScope(BaseModel):
    """Which capabilities of which zone the operator has open (UCM-14).

    Explicit and never defaulted to "all". One request explains one capability and
    takes minutes on the reference CPU machine, so explaining a whole zone eagerly
    would put minutes of P1 in front of a P0 result. The operator opens a
    capability; that capability is explained.
    """

    model_config = ConfigDict(extra="forbid")

    zone_id: str = Field(description="Zona del perfil en la que se está componiendo.")
    capability_ids: list[str] = Field(
        min_length=1,
        description="Capacidades abiertas en la interfaz, las únicas que se explican.",
    )


class CandidatesRequest(BaseModel):
    """Body of `POST /candidates`: a profile, and how widely to look."""

    model_config = ConfigDict(extra="forbid")

    profile: AssetProfile | None = Field(
        default=None,
        description="Perfil revisado por el operador. Excluyente con 'profile_id'.",
    )
    profile_id: str | None = Field(
        default=None,
        description="Identificador de un perfil congelado en el repositorio (p. ej. 'PROFILE-A').",
    )
    retrieval: bool = Field(
        default=True,
        description=(
            "Ejecutar la búsqueda de controles similares. Desactivarla no recorta la línea "
            "base: deja solo los candidatos del catálogo, y la respuesta lo declara."
        ),
    )
    lens: PayloadFilter | None = Field(
        default=None,
        description=(
            "Lente declarada sobre la búsqueda (jurisdicción, marco, tipo de mapeo). El motor "
            "nunca la aplica por iniciativa propia, y lo que aparta se devuelve igualmente, "
            "marcado como apartado."
        ),
    )
    explain: ExplainScope | None = Field(
        default=None,
        description=(
            "Capacidades para las que se pide una explicación del asistente. Es presentacional "
            "y opcional: no altera el orden ni la selección."
        ),
    )


class RetrievalStatus(str, Enum):
    """Whether the RAG pass ran, and if not, why. Never silent."""

    OK = "ok"
    # The caller asked for catalog candidates only.
    DISABLED = "disabled"
    # Qdrant unreachable or the collection could not be built. The deterministic
    # candidates are served regardless — retrieval widens, so its absence narrows
    # nothing that the catalog itself offered.
    UNAVAILABLE = "unavailable"


class RetrievalReport(BaseModel):
    """What the RAG pass contributed to this response, or why it contributed nothing."""

    model_config = ConfigDict(extra="forbid")

    status: RetrievalStatus
    suggestions: int = 0
    set_aside: int = 0
    below_cut: int = 0
    displaced: int = 0
    provenance: RetrievalProvenance | None = None
    notice: str | None = None

    @model_validator(mode="after")
    def _a_pass_that_did_not_run_says_why(self) -> RetrievalReport:
        if self.status is not RetrievalStatus.OK and not self.notice:
            raise ValueError(
                f"la recuperación es '{self.status.value}' sin explicación: una pasada que no "
                "se ejecutó tiene que decirlo (invariante 2)"
            )
        return self


class CapabilityCandidates(BaseModel):
    """One capability in one zone, with every option the human may choose from."""

    model_config = ConfigDict(extra="forbid")

    capability_id: str
    capability_name: str
    zone_id: str
    # The deterministic core, carried through verbatim. `resolution.options` is the
    # side-by-side list proper: framework, jurisdiction, strength, mapping type and
    # coverage weight of each candidate, plus the status the core gave it.
    resolution: CapabilityResolution
    gating: CapabilityGating
    priority: CapabilityPriority
    # Null when the RAG pass did not run for this response (see `RetrievalReport`).
    retrieval: CapabilityRetrieval | None = None
    # Null unless this capability was in the request's `explain` scope. Strictly
    # presentational: it cannot add, drop or reorder a candidate.
    explanations: CapabilityExplanations | None = None
    # Catalog options first, in the core's order, then the retrieved suggestions.
    offered_control_ids: list[str] = Field(default_factory=list)
    rationale: str

    @model_validator(mode="after")
    def _nothing_offered_by_the_core_disappears(self) -> CapabilityCandidates:
        offered = set(self.offered_control_ids)
        dropped = [o.control_id for o in self.resolution.options if o.control_id not in offered]
        if dropped:
            raise ValueError(
                f"{self.capability_id} en {self.zone_id} no ofrece {dropped}, que el núcleo "
                "determinista sí había mapeado: la API no recorta candidatos"
            )
        return self

    @model_validator(mode="after")
    def _an_empty_capability_is_a_declared_gap(self) -> CapabilityCandidates:
        if self.offered_control_ids:
            return self
        declared = (
            self.resolution.gap is not None
            or self.gating.gap is not None
            or (self.retrieval is not None and self.retrieval.gap is not None)
        )
        if not declared:
            raise ValueError(
                f"{self.capability_id} en {self.zone_id} no tiene ningún candidato y no declara "
                "hueco: eso es una omisión silenciosa (invariante 2)"
            )
        return self


class ZoneCandidates(BaseModel):
    """Every capability of the catalog for one zone, with the zone's own roadmap."""

    model_config = ConfigDict(extra="forbid")

    zone: ZoneContext
    capabilities: list[CapabilityCandidates] = Field(default_factory=list)
    phases: list[RoadmapPhase] = Field(default_factory=list)
    # Real contradictions the engine must not settle: they go to the human as they
    # are, and they are the reason a "most restrictive wins" rule was refused.
    open_decisions: list[Conflict] = Field(default_factory=list)
    # Tier 0 of this zone is complete — the pre-signature condition of UCM-16,
    # reported here so the operator sees it while composing, not at signing time.
    tier_0_complete: bool
    outstanding_capability_ids: list[str] = Field(default_factory=list)
    rationale: str

    def capability(self, capability_id: str) -> CapabilityCandidates:
        for capability in self.capabilities:
            if capability.capability_id == capability_id:
                return capability
        raise KeyError(f"capability not offered in {self.zone.zone_id}: {capability_id}")


class CandidatesResponse(BaseModel):
    """Response of `POST /candidates`: the run, its versions, and the options per zone.

    `run_id` is the handle the whole composition hangs from. The engine's decisions
    behind this response are already in the ledger when it is returned, and
    `POST /baseline/compose` (UCM-16) quotes this same id so the human's choices
    chain onto the run they were made from.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: UUID
    profile_id: str
    profile_name: str
    catalog_version: str
    rules_version: str
    gating_version: str
    prioritization_version: str
    retrieval: RetrievalReport
    # Why the requested explanations are absent, when they are. The candidates and
    # their deterministic justifications are on screen either way.
    explanations_notice: str | None = None
    zones: list[ZoneCandidates] = Field(default_factory=list)
    tier_0_complete: bool
    # How many entries this run appended to the append-only log (UCM-11). Reported
    # so a caller can check that the decisions it is reading were recorded.
    audit_events: int = 0

    def zone(self, zone_id: str) -> ZoneCandidates:
        for zone in self.zones:
            if zone.zone.zone_id == zone_id:
                return zone
        raise KeyError(f"zone not offered: {zone_id}")
