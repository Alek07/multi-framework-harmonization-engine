"""UCM-15 - The candidates use case: one run of everything the human chooses from.

The service is an *assembly*, not a new step of the engine. It runs the
deterministic core (UCM-8/9/10), widens with the RAG pass (UCM-13), optionally
asks for prose (UCM-14) and records the whole thing in the append-only log
(UCM-11). It computes no coverage of its own, resolves no conflict of its own and
ranks nothing: if this module were deleted, every number in the response would
still be produced somewhere else.

Four decisions are worth writing down, because each of them is a place where an
API layer could quietly break an invariant of the project.

* **The core runs before anything optional, and its result is what is served.**
  Retrieval and explanations are additive by construction; neither is allowed to
  be a precondition for answering. A machine with Qdrant down still gets the whole
  deterministic baseline, with `retrieval.status = unavailable` saying so.
* **The engine's decisions are on the record before the response leaves.**
  `record_core_run` and `record_retrieval` are awaited here, not left to the
  caller, and the `run_id` they were filed under is returned. A decision the
  operator can read but the ledger cannot is exactly what invariant 5 forbids.
* **The engine applies no lens of its own.** `request.lens` is the operator's
  question; absent it, retrieval runs over the whole index. Narrowing what the
  human is allowed to see, uninvited, is the failure UCM-13 exists to prevent.
* **CPU work goes to a worker thread.** The core, the encoder and the Qdrant
  client are synchronous and CPU-bound (69 controls to embed per query round).
  `asyncio.to_thread` keeps the event loop free instead of pretending this is I/O.
"""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

from app.assets.schemas import AssetProfile
from app.audit.service import AuditService
from app.candidates.schemas import (
    CandidatesRequest,
    CandidatesResponse,
    CapabilityCandidates,
    ExplainScope,
    RetrievalReport,
    RetrievalStatus,
    ZoneCandidates,
)
from app.catalog.loader import get_catalog
from app.core.exceptions import AppException
from app.engine.schemas import (
    CapabilityGating,
    CapabilityPriority,
    CapabilityResolution,
    PriorityTier,
    ProfileGating,
    ProfilePrioritization,
    ProfileResolution,
    ZoneResolution,
)
from app.engine.service import gate_profile, prioritize_profile, resolve_profile
from app.explain.schemas import CapabilityExplanations, ZoneExplanations
from app.explain.service import CandidateExplanationService
from app.retrieval.index import IndexUnavailableError
from app.retrieval.schemas import CapabilityRetrieval, ProfileRetrieval, ZoneRetrieval
from app.retrieval.service import RetrievalService

RETRIEVAL_DISABLED_NOTICE = (
    "La pasada RAG no se ejecutó porque la petición la desactivó ('retrieval': false). Se "
    "ofrecen los candidatos mapeados en el catálogo, íntegros: desactivar la recuperación no "
    "recorta la línea base, solo renuncia a las sugerencias adicionales."
)

EXPLAIN_NEEDS_RETRIEVAL_NOTICE = (
    "No se generan explicaciones porque la pasada RAG no se ejecutó: la explicación describe "
    "el conjunto completo de candidatos ofrecidos, y sin recuperación ese conjunto no está "
    "cerrado. Cada candidato conserva la justificación determinista del motor."
)


class UnknownZoneError(AppException):
    """The request asked about a zone the profile does not declare."""

    status_code = 422


class UnknownCapabilityError(AppException):
    """The request asked to explain a capability the catalog does not resolve here."""

    status_code = 422


class CandidatesService:
    """Profile in, every option per capability out. Collaborators are injectable.

    Both collaborators are built lazily: constructing them loads the catalog into
    a Qdrant client and builds a Pydantic AI agent, and the API must be able to
    come up — and serve `/health` — on a machine where neither service is running.
    """

    def __init__(
        self,
        retrieval: RetrievalService | None = None,
        explainer: CandidateExplanationService | None = None,
    ):
        self._retrieval = retrieval
        self._explainer = explainer

    @property
    def retrieval(self) -> RetrievalService:
        if self._retrieval is None:
            self._retrieval = RetrievalService()
        return self._retrieval

    @property
    def explainer(self) -> CandidateExplanationService:
        if self._explainer is None:
            self._explainer = CandidateExplanationService()
        return self._explainer

    # --- entry point ----------------------------------------------------------

    async def candidates_for(
        self,
        profile: AssetProfile,
        request: CandidatesRequest,
        audit: AuditService,
        run_id: UUID | None = None,
    ) -> CandidatesResponse:
        """Run the pipeline for one profile and return everything the human may choose."""
        run_id = run_id if run_id is not None else uuid4()
        self._check_scope(profile, request.explain)

        resolution, gating, prioritization = await asyncio.to_thread(self._core, profile)
        recorded = len(
            await audit.record_core_run(profile, resolution, gating, prioritization, run_id)
        )

        retrieval, report = await self._retrieve(resolution, request)
        if retrieval is not None:
            recorded += len(await audit.record_retrieval(retrieval, run_id))

        explanations, notice = await self._explain(resolution, retrieval, request.explain)

        return self._assemble(
            run_id=run_id,
            resolution=resolution,
            gating=gating,
            prioritization=prioritization,
            retrieval=retrieval,
            report=report,
            explanations=explanations,
            explanations_notice=notice,
            audit_events=recorded,
        )

    # --- the three passes -----------------------------------------------------

    def _core(
        self, profile: AssetProfile
    ) -> tuple[ProfileResolution, ProfileGating, ProfilePrioritization]:
        """Steps 1-4, chained so all four are readings of the *same* run."""
        resolution = resolve_profile(profile)
        gating = gate_profile(profile, resolution)
        prioritization = prioritize_profile(profile, gating)
        return resolution, gating, prioritization

    async def _retrieve(
        self, resolution: ProfileResolution, request: CandidatesRequest
    ) -> tuple[ProfileRetrieval | None, RetrievalReport]:
        """Widen the core's candidates, or declare why nothing was added.

        `IndexUnavailableError` is caught rather than propagated on purpose. The
        deterministic candidates are already computed at this point, and refusing
        to serve them because an optional widening failed would hide a complete
        baseline behind a convenience. What must not happen is the operator not
        *knowing*, which is why the failure travels in the response.
        """
        if not request.retrieval:
            return None, RetrievalReport(
                status=RetrievalStatus.DISABLED, notice=RETRIEVAL_DISABLED_NOTICE
            )

        try:
            retrieval = await asyncio.to_thread(
                self.retrieval.retrieve_profile, resolution, request.lens
            )
        except IndexUnavailableError as exc:
            return None, RetrievalReport(
                status=RetrievalStatus.UNAVAILABLE,
                notice=(
                    f"El índice del catálogo no está disponible ({exc.detail}). Se ofrecen los "
                    "candidatos del catálogo, íntegros y con su justificación determinista; lo "
                    "que falta son las sugerencias adicionales, que solo amplían."
                ),
            )

        return retrieval, RetrievalReport(
            status=RetrievalStatus.OK,
            suggestions=retrieval.suggestions,
            set_aside=len(retrieval.set_aside),
            provenance=retrieval.provenance,
        )

    async def _explain(
        self,
        resolution: ProfileResolution,
        retrieval: ProfileRetrieval | None,
        scope: ExplainScope | None,
    ) -> tuple[ZoneExplanations | None, str | None]:
        """Prose for the capabilities the operator has open. P1, and it fails open."""
        if scope is None:
            return None, None
        if retrieval is None:
            return None, EXPLAIN_NEEDS_RETRIEVAL_NOTICE

        explained = await self.explainer.explain_zone(
            resolution.zone(scope.zone_id),
            retrieval.zone(scope.zone_id),
            resolution.catalog_version,
            scope.capability_ids,
        )
        return explained, None

    # --- assembly -------------------------------------------------------------

    def _assemble(
        self,
        *,
        run_id: UUID,
        resolution: ProfileResolution,
        gating: ProfileGating,
        prioritization: ProfilePrioritization,
        retrieval: ProfileRetrieval | None,
        report: RetrievalReport,
        explanations: ZoneExplanations | None,
        explanations_notice: str | None,
        audit_events: int,
    ) -> CandidatesResponse:
        # Explanations are requested for one zone at a time (UCM-14): they attach
        # to that zone's capabilities and to no others.
        explained = (
            {e.capability_id: e for e in explanations.capabilities}
            if explanations is not None
            else {}
        )
        explained_zone = explanations.zone_id if explanations is not None else None

        zones = [
            self._zone(
                zone,
                gating,
                prioritization,
                retrieval.zone(zone.zone.zone_id) if retrieval is not None else None,
                explained if zone.zone.zone_id == explained_zone else {},
            )
            for zone in resolution.zones
        ]

        return CandidatesResponse(
            run_id=run_id,
            profile_id=resolution.profile_id,
            profile_name=resolution.profile_name,
            catalog_version=resolution.catalog_version,
            rules_version=resolution.rules_version,
            gating_version=gating.gating_version,
            prioritization_version=prioritization.prioritization_version,
            retrieval=report,
            explanations_notice=explanations_notice,
            zones=zones,
            tier_0_complete=prioritization.tier_0_complete,
            audit_events=audit_events,
        )

    def _zone(
        self,
        zone: ZoneResolution,
        gating: ProfileGating,
        prioritization: ProfilePrioritization,
        retrieval: ZoneRetrieval | None,
        explained: dict[str, CapabilityExplanations],
    ) -> ZoneCandidates:
        zone_id = zone.zone.zone_id
        zone_gating = gating.zone(zone_id)
        zone_priorities = prioritization.zone(zone_id)

        capabilities = [
            self._capability(
                capability,
                zone_gating.capability(capability.capability.id),
                zone_priorities.capability(capability.capability.id),
                retrieval.capability(capability.capability.id) if retrieval is not None else None,
                explained.get(capability.capability.id),
            )
            for capability in zone.capabilities
        ]

        outstanding = [c.capability_id for c in zone_priorities.outstanding_mandates]
        return ZoneCandidates(
            zone=zone.zone,
            capabilities=capabilities,
            phases=zone_priorities.phases,
            open_decisions=zone.open_decisions,
            tier_0_complete=zone_priorities.tier_0_complete,
            outstanding_capability_ids=outstanding,
            rationale=self._zone_rationale(zone, zone_priorities.tier_0_complete, capabilities),
        )

    def _capability(
        self,
        resolution: CapabilityResolution,
        gating: CapabilityGating,
        priority: CapabilityPriority,
        retrieval: CapabilityRetrieval | None,
        explanations: CapabilityExplanations | None,
    ) -> CapabilityCandidates:
        offered = (
            retrieval.offered_control_ids
            if retrieval is not None
            else [option.control_id for option in resolution.options]
        )
        return CapabilityCandidates(
            capability_id=resolution.capability.id,
            capability_name=resolution.capability.name,
            zone_id=resolution.zone_id,
            resolution=resolution,
            gating=gating,
            priority=priority,
            retrieval=retrieval,
            explanations=explanations,
            offered_control_ids=offered,
            rationale=self._capability_rationale(resolution, priority, retrieval, offered),
        )

    # --- operator-facing text -------------------------------------------------

    def _capability_rationale(
        self,
        resolution: CapabilityResolution,
        priority: CapabilityPriority,
        retrieval: CapabilityRetrieval | None,
        offered: list[str],
    ) -> str:
        name = resolution.capability.name
        catalog = len(resolution.options)
        suggested = len(retrieval.widening) if retrieval is not None else 0
        tier = (
            "Tier 0 (obligatorio por el SL-objetivo de la zona)"
            if priority.tier is PriorityTier.TIER_0
            else "Tier 1 (discrecional)"
        )

        head = (
            f"«{name}» en {resolution.zone_id}: {catalog} candidato(s) del catálogo y "
            f"{suggested} sugerencia(s) de recuperación, {len(offered)} opción(es) en total. "
            f"{tier}, fase {priority.phase}."
        )
        if not offered:
            return head + (
                " Sin ninguna opción: la capacidad sigue exigida y el hueco se declara de forma "
                "explícita para que el humano lo cierre o lo acepte por escrito."
            )
        tail = (
            " El motor no elige: las opciones se muestran con su marco, jurisdicción, tipo de "
            "mapeo y peso de cobertura, y la selección es del humano."
        )
        if priority.outstanding:
            tail += (
                " Mandato pendiente: el gating no dejó mecanismo aplicable, así que hay que "
                "cerrarlo antes de firmar."
            )
        return head + tail

    def _zone_rationale(
        self,
        zone: ZoneResolution,
        tier_0_complete: bool,
        capabilities: list[CapabilityCandidates],
    ) -> str:
        offered = sum(len(c.offered_control_ids) for c in capabilities)
        gaps = sum(1 for c in capabilities if not c.offered_control_ids)
        escalated = len(zone.open_decisions)

        text = (
            f"Zona {zone.zone.zone_id} ({zone.zone.domain.value}, SL-objetivo "
            f"{zone.zone.target_sl}): {len(capabilities)} capacidades del catálogo, "
            f"{offered} opción(es) ofrecidas, {gaps} hueco(s) explícito(s). "
        )
        text += (
            "Tier 0 completo según el motor."
            if tier_0_complete
            else "Tier 0 incompleto: hay mandatos pendientes que el humano debe cerrar antes "
            "de firmar."
        )
        if escalated:
            text += (
                f" {escalated} contradicción(es) real(es) escalada(s) al humano: el motor no "
                "las resuelve por 'lo más restrictivo gana'."
            )
        return text

    # --- validation -----------------------------------------------------------

    def _check_scope(self, profile: AssetProfile, scope: ExplainScope | None) -> None:
        """Reject an unreachable explain scope *before* the pipeline runs, not after.

        The order matters, and not only for latency. The core run is appended to
        the append-only ledger as soon as it is computed, so validating afterwards
        would leave a recorded engine run behind every client typo. Both checks are
        made against declared data — the profile's zones and the catalog's
        capabilities — so neither needs the pipeline to have run.
        """
        if scope is None:
            return

        declared = [zone.id for zone in profile.zones]
        if scope.zone_id not in declared:
            raise UnknownZoneError(
                f"El perfil '{profile.id}' no declara la zona '{scope.zone_id}'. "
                f"Zonas del perfil: {declared}."
            )

        known = {capability.id for capability in get_catalog().capabilities}
        unknown = [c for c in scope.capability_ids if c not in known]
        if unknown:
            raise UnknownCapabilityError(
                f"El catálogo {get_catalog().catalog_version} no declara {unknown}. "
                "Solo se explican capacidades del catálogo."
            )
