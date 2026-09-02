from __future__ import annotations

from typing import Any
from uuid import UUID

from app.audit.schemas import AuditActor, AuditEventCreate, AuditEventType, AuditStage
from app.audit.trail import ACTOR_REFS
from app.core.wording import say, say_all
from app.retrieval.schemas import (
    CapabilityRetrieval,
    ProfileRetrieval,
    RetrievalProvenance,
    ZoneRetrieval,
)


def trail_for_retrieval(retrieval: ProfileRetrieval, run_id: UUID) -> list[AuditEventCreate]:
    """Every entry of one RAG pass, zone by zone, ready to be appended."""
    versions = _versions(retrieval.provenance)
    entries: list[AuditEventCreate] = []
    for zone in retrieval.zones:
        entries.extend(_zone(zone, retrieval, run_id, versions))
    return entries


def _zone(
    zone: ZoneRetrieval,
    retrieval: ProfileRetrieval,
    run_id: UUID,
    versions: dict[str, str],
) -> list[AuditEventCreate]:
    entries: list[AuditEventCreate] = []
    for capability in zone.capabilities:
        entries.append(_candidates_retrieved(capability, retrieval, run_id, versions))
        entries.extend(_candidates_cut(capability, retrieval, run_id, versions))
        entries.extend(_set_aside(capability, retrieval, run_id, versions))
        if capability.gap is not None:
            entries.append(_gap_declared(capability, retrieval, run_id, versions))
    entries.append(_stage_completed(zone, retrieval, run_id, versions))
    return entries


def _candidates_retrieved(
    capability: CapabilityRetrieval,
    retrieval: ProfileRetrieval,
    run_id: UUID,
    versions: dict[str, str],
) -> AuditEventCreate:
    widening = capability.widening
    decision = (
        f"«{capability.capability_name}» en {capability.zone_id}: "
        f"{len(capability.catalog_control_ids)} candidato(s) del catálogo + "
        f"{len(widening)} sugerencia(s) recuperada(s)"
    )
    return _event(
        AuditEventType.CANDIDATES_RETRIEVED,
        decision,
        f"{capability.rationale} La recuperación es aditiva por construcción: los candidatos del "
        "catálogo se registran aquí íntegros junto a los recuperados, de modo que en la bitácora "
        "el número de opciones después de esta pasada nunca puede ser menor que antes.",
        run_id,
        retrieval.profile_id,
        versions,
        zone_id=capability.zone_id,
        capability_id=capability.capability_id,
        payload={
            "catalog_control_ids": capability.catalog_control_ids,
            "offered_control_ids": capability.offered_control_ids,
            "suggestions": [
                {
                    "control_id": hit.control_id,
                    "official_id": hit.control.official_id,
                    "framework": hit.framework.value,
                    "jurisdiction": hit.jurisdiction.value,
                    "score": hit.score,
                    "mapped_capability_ids": hit.mapped_capability_ids,
                    "rationale": hit.rationale,
                }
                for hit in widening
            ],
            "confirmations": [hit.control_id for hit in capability.confirmations],
            "set_aside": len(capability.set_aside),
        },
    )


def _candidates_cut(
    capability: CapabilityRetrieval,
    retrieval: ProfileRetrieval,
    run_id: UUID,
    versions: dict[str, str],
) -> list[AuditEventCreate]:
    """The rule that bounded the ranking, and what it left below (UCM-54).

    A list only so a capability the index never answered writes nothing at all.
    """
    cut = capability.cut
    if cut is None:
        return []
    displaced = len(cut.displaced)
    first = cut.first_dropped
    below = (
        f", el primero {first.official_id} ({first.score:.3f}, "
        f"{'+' if first.margin < 0 else '-'}{abs(first.margin):.3f} frente al último mostrado)"
        if first is not None
        else ""
    )
    return [
        _event(
            AuditEventType.CANDIDATES_CUT,
            f"Corte del recuperador en «{capability.capability_name}» ({capability.zone_id}): "
            f"{cut.retained} retenida(s) de {cut.evaluated} evaluada(s), {cut.dropped} bajo el "
            f"corte{below}, {displaced} desplazada(s) por el tope de marco",
            f"{cut.rationale} El corte del recuperador lleva regla, parámetros y versión, igual "
            "que el gating y la precedencia: lo que queda fuera se cuenta, el primero se nombra "
            "con su similitud y lo que desplaza el tope se lista uno a uno. No es un umbral de "
            "puntuación y no toca la línea base — acota sugerencias, y los candidatos del "
            "catálogo lo atraviesan intactos.",
            run_id,
            retrieval.profile_id,
            versions,
            zone_id=capability.zone_id,
            capability_id=capability.capability_id,
            payload=cut.model_dump(mode="json"),
        )
    ]


def _set_aside(
    capability: CapabilityRetrieval,
    retrieval: ProfileRetrieval,
    run_id: UUID,
    versions: dict[str, str],
) -> list[AuditEventCreate]:
    return [
        _event(
            AuditEventType.CANDIDATE_SET_ASIDE,
            f"{candidate.official_id} ({candidate.framework.value}) apartado de "
            f"«{capability.capability_name}» en {capability.zone_id} por "
            f"{say_all(candidate.excluded_by)}",
            f"{candidate.rationale} Queda en el registro con su similitud y el eje que lo apartó: "
            "una lente declarada acota la vista del operador, nunca la línea base, y lo que deja "
            "fuera es recuperable de la propia bitácora.",
            run_id,
            retrieval.profile_id,
            versions,
            zone_id=capability.zone_id,
            capability_id=capability.capability_id,
            control_id=candidate.control_id,
            payload=candidate.model_dump(mode="json"),
        )
        for candidate in capability.set_aside
    ]


def _gap_declared(
    capability: CapabilityRetrieval,
    retrieval: ProfileRetrieval,
    run_id: UUID,
    versions: dict[str, str],
) -> AuditEventCreate:
    gap = capability.gap
    assert gap is not None  # guarded by the caller; the model forbids the other case
    return _event(
        AuditEventType.GAP_DECLARED,
        f"Hueco ({say(gap.kind)}) tras la recuperación en «{capability.capability_name}» "
        f"({gap.zone_id})",
        f"{gap.rationale} Se declara como hueco explícito: la meta declarada es 0 omisiones "
        "silenciosas, y una capacidad sin candidato se señala, no se calla.",
        run_id,
        retrieval.profile_id,
        versions,
        zone_id=gap.zone_id,
        capability_id=gap.capability_id,
        payload=gap.model_dump(mode="json"),
    )


def _stage_completed(
    zone: ZoneRetrieval,
    retrieval: ProfileRetrieval,
    run_id: UUID,
    versions: dict[str, str],
) -> AuditEventCreate:
    lens = retrieval.provenance.payload_filter
    return _event(
        AuditEventType.STAGE_COMPLETED,
        f"Recuperación completada en {zone.zone.zone_id}: {zone.suggestions} sugerencia(s) "
        f"sobre {len(zone.capabilities)} capacidad(es), {len(zone.set_aside)} apartada(s) por "
        f"la lente, {zone.dropped} bajo el corte",
        "La pasada de recuperación solo amplía: ningún candidato del catálogo se elimina ni se "
        "reordena, y las sugerencias se marcan como tales — no son mapeos, no tienen peso de "
        "cobertura y no "
        "entran en gating ni en priorización. Lo que una lente declarada deja fuera queda "
        "registrado candidato a candidato. Lo que el corte deja bajo el límite queda contado, con "
        "su regla y con el primer descartado nombrado. Las capacidades sin ningún candidato se "
        "declaran como hueco explícito.",
        run_id,
        retrieval.profile_id,
        versions,
        zone_id=zone.zone.zone_id,
        payload={
            "capabilities": len(zone.capabilities),
            "capability_ids": [c.capability_id for c in zone.capabilities],
            "widened_capability_ids": zone.widened_capability_ids,
            "suggestions": zone.suggestions,
            "set_aside": len(zone.set_aside),
            "below_cut": zone.dropped,
            "displaced_by_framework_cap": len(zone.displaced),
            "gaps": len(zone.gaps),
            "gap_capability_ids": [gap.capability_id for gap in zone.gaps],
            "lens_active": lens.is_active,
            "lens": lens.describe(),
            "collection": retrieval.provenance.collection,
        },
    )


def _event(
    event_type: AuditEventType,
    decision: str,
    rationale: str,
    run_id: UUID,
    profile_id: str,
    versions: dict[str, str],
    *,
    zone_id: str | None = None,
    capability_id: str | None = None,
    control_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> AuditEventCreate:
    return AuditEventCreate(
        actor=AuditActor.ENGINE,
        actor_ref=ACTOR_REFS[AuditStage.RETRIEVAL],
        stage=AuditStage.RETRIEVAL,
        event_type=event_type,
        run_id=run_id,
        profile_id=profile_id,
        zone_id=zone_id,
        capability_id=capability_id,
        control_id=control_id,
        decision=decision,
        rationale=rationale,
        versions=versions,
        payload=payload or {},
    )


def _versions(provenance: RetrievalProvenance) -> dict[str, str]:
    """Which vectors answered this pass — model, template and collection included.

    The collection name carries the catalog digest, so an entry logged here says
    not only *which* catalog governed the retrieval but that the vectors were
    built from that exact catalog.
    """
    return {
        "catalog": provenance.catalog_version,
        "embedding_model": provenance.embedding_model,
        "text_template": provenance.text_template_version,
        "collection": provenance.collection,
        "cut_policy": provenance.cut_policy.version,
    }
