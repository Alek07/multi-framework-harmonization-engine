from __future__ import annotations

from app.core.config import settings
from app.core.wording import say_all
from app.engine.schemas import (
    CapabilityGap,
    CapabilityResolution,
    GapKind,
    ProfileGating,
    ProfileResolution,
    ZoneContext,
    ZoneGating,
    ZoneResolution,
)
from app.retrieval.cut import apply_cut, current_policy
from app.retrieval.embeddings import TEXT_TEMPLATE_VERSION, capability_text
from app.retrieval.filters import excluded_axes, to_qdrant
from app.retrieval.index import CatalogIndex, IndexHit
from app.retrieval.schemas import (
    CapabilityRetrieval,
    GatingAnnotation,
    PayloadFilter,
    ProfileRetrieval,
    RetrievalCut,
    RetrievalProvenance,
    RetrievalRelation,
    RetrievedControl,
    SetAsideCandidate,
    ZoneRetrieval,
    sink_gated,
)


class RetrievalService:
    """Catalog resolution in, additional candidates out. The index is injectable."""

    def __init__(self, index: CatalogIndex | None = None):
        self.index = index if index is not None else CatalogIndex()

    # --- entry points ---------------------------------------------------------

    def retrieve_profile(
        self,
        resolution: ProfileResolution,
        payload_filter: PayloadFilter | None = None,
        *,
        gating: ProfileGating | None = None,
    ) -> ProfileRetrieval:
        """Widen the candidates of every capability in every zone of the profile.

        `gating` is the deterministic core's step 3. When present, a suggestion for a
        mechanism gating ruled out of the zone is *annotated* with that exclusion
        rather than offered as if it applied. Absent, retrieval widens as before.
        """
        self._check_same_catalog(resolution)
        lens = payload_filter if payload_filter is not None else PayloadFilter()

        return ProfileRetrieval(
            profile_id=resolution.profile_id,
            profile_name=resolution.profile_name,
            catalog_version=self.index.catalog.catalog_version,
            provenance=self.provenance(lens),
            zones=[
                self.retrieve_zone(
                    zone,
                    lens,
                    gating=gating.zone(zone.zone.zone_id) if gating is not None else None,
                )
                for zone in resolution.zones
            ],
        )

    def retrieve_zone(
        self,
        zone: ZoneResolution,
        payload_filter: PayloadFilter | None = None,
        *,
        gating: ZoneGating | None = None,
    ) -> ZoneRetrieval:
        """Widen every capability of one zone, in the resolution's own order.

        The lens the caller hands in is augmented here with the zone's own sectoral
        applicability: what the norm's declared scope leaves out of this zone comes
        back set aside on the sector axis, the same as any other lens.
        """
        lens = self._applicability_lens(
            zone.zone, payload_filter if payload_filter is not None else PayloadFilter()
        )
        gated = self._zone_gated_controls(gating)
        return ZoneRetrieval(
            zone=zone.zone,
            capabilities=[
                self.retrieve_capability(capability, lens, gated=gated)
                for capability in zone.capabilities
            ],
        )

    def retrieve_capability(
        self,
        capability: CapabilityResolution,
        payload_filter: PayloadFilter | None = None,
        *,
        gated: dict[str, GatingAnnotation] | None = None,
    ) -> CapabilityRetrieval:
        """The pass itself, for one capability in one zone."""
        lens = payload_filter if payload_filter is not None else PayloadFilter()
        gated = gated if gated is not None else {}

        # Every option the core offered, including the ones a contradiction left
        # `superseded`: they are still visible to the operator, so re-offering one
        # as a "new" suggestion would be a false discovery.
        catalog_control_ids = [option.control_id for option in capability.options]

        query = capability_text(capability.capability)
        # Wider than the cut keeps: a candidate the index never returned cannot be reported.
        depth = settings.RAG_RETRIEVAL_DEPTH + len(catalog_control_ids)
        query_filter = to_qdrant(lens)

        hits = self.index.search(query, depth, query_filter)
        confirmations = {h.control_id for h in hits if h.control_id in set(catalog_control_ids)}
        kept, cut = apply_cut(
            [hit for hit in hits if hit.control_id not in confirmations],
            capability_name=capability.capability.name,
            indexed_controls=self.index.indexed_controls,
            policy=current_policy(depth),
        )

        # Rebuilt from `hits` so confirmations and suggestions keep one shared
        # ranking, and then ordered by the declared rule: a suggestion the zone's
        # gating already ruled out reads last, and reads marked. The sort happens
        # *after* `apply_cut`, so it can move a suggestion but never decide whether
        # it survives — that is the cut's call, not this one's.
        shown = confirmations | {hit.control_id for hit in kept}
        retrieved = sink_gated(
            [
                self._as_candidate(hit, capability, catalog_control_ids, gated)
                for hit in hits
                if hit.control_id in shown
            ]
        )

        set_aside = (
            self._set_aside(query, depth, lens, capability, catalog_control_ids)
            if lens.is_active
            else []
        )

        widening = [r for r in retrieved if r.relation is RetrievalRelation.WIDENS]
        gap = (
            self._gap(capability)
            if not catalog_control_ids and not widening
            else None
        )

        return CapabilityRetrieval(
            capability_id=capability.capability.id,
            capability_name=capability.capability.name,
            zone_id=capability.zone_id,
            catalog_control_ids=catalog_control_ids,
            retrieved=retrieved,
            set_aside=set_aside,
            cut=cut if retrieved else None,
            gap=gap,
            rationale=self._rationale(
                capability, catalog_control_ids, widening, set_aside, lens, cut
            ),
        )

    # --- provenance -----------------------------------------------------------

    def provenance(self, payload_filter: PayloadFilter | None = None) -> RetrievalProvenance:
        """Which vectors, built from which catalog, under which lens."""
        return RetrievalProvenance(
            embedding_model=settings.EMBEDDING_MODEL,
            embedding_dim=settings.EMBEDDING_DIM,
            collection=self.index.collection,
            catalog_version=self.index.catalog.catalog_version,
            catalog_digest=self.index.digest,
            indexed_controls=self.index.indexed_controls,
            text_template_version=TEXT_TEMPLATE_VERSION,
            top_k=settings.RAG_TOP_K,
            # The base depth; each capability's `cut.policy` carries its effective one.
            cut_policy=current_policy(),
            payload_filter=payload_filter if payload_filter is not None else PayloadFilter(),
        )

    # --- internals ------------------------------------------------------------

    def _as_candidate(
        self,
        hit: IndexHit,
        capability: CapabilityResolution,
        catalog_control_ids: list[str],
        gated: dict[str, GatingAnnotation],
    ) -> RetrievedControl:
        already_mapped = hit.control_id in catalog_control_ids
        relation = (
            RetrievalRelation.CONFIRMS_MAPPING if already_mapped else RetrievalRelation.WIDENS
        )
        payload = hit.payload
        name = capability.capability.name

        # A suggestion (never a confirmation, whose gating is already on the record
        # in `CapabilityGating`) for a mechanism gating ruled out of this zone.
        gated_out = None if already_mapped else gated.get(hit.control_id)

        if already_mapped:
            rationale = (
                f"Confirmación: el catálogo ya ofrece {payload.official_id} "
                f"({payload.framework}) para «{name}». La recuperación lo reencuentra por "
                f"similitud {hit.score:.3f}; no añade cobertura, respalda la que ya estaba."
            )
        else:
            elsewhere = ", ".join(payload.capability_ids) or "ninguna capacidad"
            rationale = (
                f"Sugerencia: el catálogo no mapea {payload.official_id} ({payload.framework}, "
                f"{payload.jurisdiction}) a «{name}» — lo mapea a {elsewhere}. Similitud "
                f"{hit.score:.3f} sobre el texto del control. No es un mapeo: no altera "
                "cobertura, gating ni priorización, y solo el humano puede adoptarlo."
            )
        if gated_out is not None:
            rationale += (
                f" Atención: el gating ya excluyó este mecanismo en {gated_out.zone_id} "
                f"(regla {gated_out.rule_id}). Se muestra marcado, no oculto: adoptarlo exige "
                "la justificación compensatoria que el gating pide, y es decisión del humano."
            )

        return RetrievedControl(
            control=self.index.control(hit.control_id),
            score=hit.score,
            relation=relation,
            mapped_capability_ids=payload.capability_ids,
            mapping_types=payload.mapping_types,  # type: ignore[arg-type]
            gated_out=gated_out,
            rationale=rationale,
        )

    def _applicability_lens(self, zone: ZoneContext, operator_lens: PayloadFilter) -> PayloadFilter:
        """The operator's lens augmented with the zone's sectoral applicability.

        The engine builds this axis on its own initiative, and that is not a silent
        restriction: what the zone's sectors leave out returns set aside on the
        sector axis. With no sectors declared the engine asserts nothing — an
        exclusion on a premise nobody stated would be a false obligation — so the
        operator's lens is handed back untouched.
        """
        if not zone.sectors:
            return operator_lens
        note = (
            f"Ámbito sectorial de la zona {zone.zone_id} ({say_all(zone.sectors)}): una norma "
            "cuyo ámbito declarado no lo incluye no se sugiere como si aplicara; se aparta, "
            "marcada y trazable. Las normas transversales no se apartan."
        )
        rationale = f"{operator_lens.rationale} {note}".strip() if operator_lens.rationale else note
        return operator_lens.model_copy(update={"sectors": zone.sectors, "rationale": rationale})

    def _zone_gated_controls(self, gating: ZoneGating | None) -> dict[str, GatingAnnotation]:
        """Which controls gating ruled out of the zone, by control id.

        Gating (a rule or sectoral applicability) decides a control's fate per
        control and per zone, independently of the capability the decision was
        recorded against — so one annotation per control describes it wherever the
        retrieval later suggests it. The first decision wins; the rest say the same.
        """
        if gating is None:
            return {}
        annotations: dict[str, GatingAnnotation] = {}
        for decision in gating.decisions:
            if decision.control_id in annotations:
                continue
            annotations[decision.control_id] = GatingAnnotation(
                zone_id=decision.zone_id,
                outcome=decision.outcome,
                rule_id=decision.rule_id,
                rationale=decision.rationale,
                evidence=decision.evidence,
            )
        return annotations

    def _set_aside(
        self,
        query: str,
        limit: int,
        lens: PayloadFilter,
        capability: CapabilityResolution,
        catalog_control_ids: list[str],
    ) -> list[SetAsideCandidate]:
        """What the lens excluded from the same neighbourhood, and on which axis.

        The second query is the price of the invariant: without it the lens would
        be a narrowing nobody could see. It is run unfiltered over the same `limit`
        so the comparison is like for like.
        """
        candidates: list[SetAsideCandidate] = []
        for hit in self.index.search(query, limit, None):
            axes = excluded_axes(lens, hit.payload)
            if not axes:
                continue
            relation = (
                RetrievalRelation.CONFIRMS_MAPPING
                if hit.control_id in catalog_control_ids
                else RetrievalRelation.WIDENS
            )
            names = say_all(axes)
            candidates.append(
                SetAsideCandidate(
                    control_id=hit.control_id,
                    official_id=hit.payload.official_id,
                    framework=hit.payload.framework,  # type: ignore[arg-type]
                    jurisdiction=hit.payload.jurisdiction,  # type: ignore[arg-type]
                    score=hit.score,
                    relation=relation,
                    excluded_by=axes,
                    rationale=(
                        f"Apartado por la lente declarada ({names}) en «"
                        f"{capability.capability.name}»: {lens.describe()}. Se registra con su "
                        "similitud para que la lente sea auditable — apartar no es descartar, y "
                        "la línea base del catálogo no cambia."
                    ),
                )
            )
        return candidates

    def _gap(self, capability: CapabilityResolution) -> CapabilityGap:
        return CapabilityGap(
            capability_id=capability.capability.id,
            zone_id=capability.zone_id,
            kind=GapKind.NO_CANDIDATE,
            coverage=0.0,
            residual=1.0,
            rationale=(
                f"Ni el catálogo ni la recuperación ofrecen candidato para «"
                f"{capability.capability.name}» en {capability.zone_id}. La capacidad sigue "
                "exigida: se declara como hueco explícito para que el humano lo cierre con un "
                "control compensatorio o lo acepte de forma justificada. La recuperación amplía "
                "cobertura, nunca la recorta: aquí no había nada que ampliar."
            ),
        )

    def _rationale(
        self,
        capability: CapabilityResolution,
        catalog_control_ids: list[str],
        widening: list[RetrievedControl],
        set_aside: list[SetAsideCandidate],
        lens: PayloadFilter,
        cut: RetrievalCut,
    ) -> str:
        name = capability.capability.name
        head = (
            f"«{name}» en {capability.zone_id}: {len(catalog_control_ids)} candidato(s) del "
            f"catálogo, {len(widening)} sugerencia(s) añadida(s) por recuperación."
        )
        if catalog_control_ids or widening:
            body = (
                " Los candidatos del catálogo se mantienen íntegros; las sugerencias se marcan "
                "como tales y no entran en el cálculo de cobertura."
            )
        else:
            body = " Sin ningún candidato: se declara hueco explícito y la capacidad sigue exigida."
        if not catalog_control_ids and widening:
            body += (
                " El hueco que declaró el núcleo determinista sigue abierto: una sugerencia no "
                "es un mapeo y solo lo cierra la decisión del humano."
            )
        tail = f" Lente: {lens.describe()}."
        if set_aside:
            tail += (
                f" {len(set_aside)} candidato(s) apartado(s) por la lente, listados y trazables."
            )
        if cut.dropped:
            tail += (
                f" Corte: {cut.dropped} candidato(s) bajo el límite, {cut.near_ties_dropped} de "
                f"ellos indistinguibles del último mostrado y "
                f"{len(cut.displaced)} desplazado(s) por el tope de marco; todos contados, y el "
                "primero nombrado con su similitud."
            )
        return head + body + tail

    def _check_same_catalog(self, resolution: ProfileResolution) -> None:
        """Refuse to widen a resolution computed from a different catalog.

        Retrieving against one catalog what another one resolved would produce
        suggestions that look authoritative and are not comparable — the exact
        kind of plausible-looking lie the audit log exists to make impossible.
        """
        indexed = self.index.catalog.catalog_version
        if resolution.catalog_version != indexed:
            raise ValueError(
                f"the resolution was computed with catalog {resolution.catalog_version} and the "
                f"index holds catalog {indexed}"
            )
