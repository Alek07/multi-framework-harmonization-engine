"""UCM-13 - The RAG pass: more options for the human, never fewer.

The service takes the deterministic core's own output (steps 1-2, `UCM-8`) and
returns what retrieval *adds* to it. It deliberately does not return a new
resolution: coverage, conflicts, gating and prioritisation stay exactly as the
core computed them, because an embedding distance is not evidence that two
controls are equivalent, and letting a similarity score reach the arithmetic of
the baseline would be the LLM layer deciding (invariant 1).

What it does, per capability and per zone:

1. asks the index for the nearest controls to the capability's own text;
2. labels each hit against the catalog — `confirms_mapping` if the author already
   mapped it here, `widens` if not;
3. when a lens is active, re-runs the same query unfiltered and reports everything
   the lens set aside, with the axis responsible;
4. declares an explicit gap when *neither* source offers a single candidate.

Step 4 is the measured invariant. A capability that reaches the end of this pass
with nothing is not dropped and not quietly left out of the result — it comes back
as a `NO_CANDIDATE` gap, the same one the deterministic core uses, and the
requirement itself remains. Silent omissions target: zero.

One consequence of having no score threshold is worth declaring rather than
discovering later. e5 similarities sit in a narrow band — on this catalog the
nearest control scores ~0.90 and the tenth ~0.83 — so `RAG_TOP_K` is filled for
essentially every capability, and the tail of that list is weak. That is the
intended trade: a threshold would drop candidates without saying so, and the
operator can ignore a weak suggestion but cannot ask for one that was never
shown. Ranking is what separates the good suggestions from the rest, and how
often the tail is actually accepted is a number for the evaluation to report
(UCM-18), not one to pre-empt with a cut-off chosen by feel.
"""

from __future__ import annotations

from app.core.config import settings
from app.core.wording import say_all
from app.engine.schemas import (
    CapabilityGap,
    CapabilityResolution,
    GapKind,
    ProfileResolution,
    ZoneResolution,
)
from app.retrieval.embeddings import TEXT_TEMPLATE_VERSION, capability_text
from app.retrieval.filters import excluded_axes, to_qdrant
from app.retrieval.index import CatalogIndex, IndexHit
from app.retrieval.schemas import (
    CapabilityRetrieval,
    PayloadFilter,
    ProfileRetrieval,
    RetrievalProvenance,
    RetrievalRelation,
    RetrievedControl,
    SetAsideCandidate,
    ZoneRetrieval,
)


class RetrievalService:
    """Catalog resolution in, additional candidates out. The index is injectable."""

    def __init__(self, index: CatalogIndex | None = None):
        self.index = index if index is not None else CatalogIndex()

    # --- entry points ---------------------------------------------------------

    def retrieve_profile(
        self, resolution: ProfileResolution, payload_filter: PayloadFilter | None = None
    ) -> ProfileRetrieval:
        """Widen the candidates of every capability in every zone of the profile."""
        self._check_same_catalog(resolution)
        lens = payload_filter if payload_filter is not None else PayloadFilter()

        return ProfileRetrieval(
            profile_id=resolution.profile_id,
            profile_name=resolution.profile_name,
            catalog_version=self.index.catalog.catalog_version,
            provenance=self.provenance(lens),
            zones=[self.retrieve_zone(zone, lens) for zone in resolution.zones],
        )

    def retrieve_zone(
        self, zone: ZoneResolution, payload_filter: PayloadFilter | None = None
    ) -> ZoneRetrieval:
        """Widen every capability of one zone, in the resolution's own order."""
        lens = payload_filter if payload_filter is not None else PayloadFilter()
        return ZoneRetrieval(
            zone=zone.zone,
            capabilities=[
                self.retrieve_capability(capability, lens) for capability in zone.capabilities
            ],
        )

    def retrieve_capability(
        self, capability: CapabilityResolution, payload_filter: PayloadFilter | None = None
    ) -> CapabilityRetrieval:
        """The pass itself, for one capability in one zone."""
        lens = payload_filter if payload_filter is not None else PayloadFilter()

        # Every option the core offered, including the ones a contradiction left
        # `superseded`: they are still visible to the operator, so re-offering one
        # as a "new" suggestion would be a false discovery.
        catalog_control_ids = [option.control_id for option in capability.options]

        query = capability_text(capability.capability)
        # Enough room for `RAG_TOP_K` genuinely new candidates even in the case
        # where every catalog candidate comes back as a confirmation.
        limit = settings.RAG_TOP_K + len(catalog_control_ids)
        query_filter = to_qdrant(lens)

        hits = self.index.search(query, limit, query_filter)
        retrieved = [self._as_candidate(hit, capability, catalog_control_ids) for hit in hits]

        set_aside = (
            self._set_aside(query, limit, lens, capability, catalog_control_ids)
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
            gap=gap,
            rationale=self._rationale(capability, catalog_control_ids, widening, set_aside, lens),
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
            payload_filter=payload_filter if payload_filter is not None else PayloadFilter(),
        )

    # --- internals ------------------------------------------------------------

    def _as_candidate(
        self,
        hit: IndexHit,
        capability: CapabilityResolution,
        catalog_control_ids: list[str],
    ) -> RetrievedControl:
        already_mapped = hit.control_id in catalog_control_ids
        relation = (
            RetrievalRelation.CONFIRMS_MAPPING if already_mapped else RetrievalRelation.WIDENS
        )
        payload = hit.payload
        name = capability.capability.name

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

        return RetrievedControl(
            control=self.index.control(hit.control_id),
            score=hit.score,
            relation=relation,
            mapped_capability_ids=payload.capability_ids,
            mapping_types=payload.mapping_types,  # type: ignore[arg-type]
            rationale=rationale,
        )

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
