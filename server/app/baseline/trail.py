"""UCM-16 - The human's half of the ledger: what was composed, and on whose word.

`audit/trail.py` derives the engine's entries and `retrieval/trail.py` the RAG
pass's. This derives the operator's, and it is the one place in the system where
the actor is a person. Everything here is pure: the same composition over the same
run always produces the same entries, in the same order, with the same texts —
only `sequence`, `recorded_at` and the hashes come from the ledger.

Three properties are what make the trail worth the claim the TFM rests on.

* **Every mandatory capability leaves a human-authored entry.** Chosen,
  compensated, accepted as a gap, or ratified — but never absent. A mandatory
  mechanism cannot end up in a signed baseline with nobody's name on it.
* **Ratifying is not choosing, and the log says which happened.**
  `MECHANISM_RATIFIED` carries the operator's signature rationale and the engine's
  own gating rationale, and says plainly that no selection among equivalents took
  place. `OPTION_SELECTED` is written only when the operator actually picked.
* **An adopted suggestion is never laundered into a mapping.** When the chosen
  control is one the catalog does not map to that capability, the entry records
  it as `adopted_suggestion` with that fact in the payload. An embedding distance
  does not become authored evidence because a human agreed with it — what makes it
  admissible is the human's written reason, and that is what is stored.
"""

from __future__ import annotations

from typing import Any

from app.audit.schemas import AuditActor, AuditEventCreate, AuditEventType, AuditStage
from app.baseline.schemas import (
    ChoiceKind,
    ComposedBaseline,
    ComposedCapability,
    ComposedZone,
    CompositionChoice,
    SelectionOrigin,
    Signature,
)
from app.core.wording import say
from app.engine.schemas import PriorityTier

# The operator is the actor; this is the component that filed the entry for them.
ACTOR_REF = "human.composition"

CHOICE_EVENTS: dict[ChoiceKind, AuditEventType] = {
    ChoiceKind.OPTION_SELECTED: AuditEventType.OPTION_SELECTED,
    ChoiceKind.OPTION_REJECTED: AuditEventType.OPTION_REJECTED,
    ChoiceKind.COMPENSATORY_DECLARED: AuditEventType.COMPENSATORY_DECLARED,
    ChoiceKind.GAP_ACCEPTED: AuditEventType.GAP_ACCEPTED,
}

RATIFICATION_NOTE = (
    "Ratificación, no selección: el operador no eligió entre equivalentes aquí — aceptó, al "
    "firmar, el mecanismo que el núcleo determinista ya había retenido para un mandato que no "
    "quedaba pendiente. Se registra con tipo propio para que la bitácora nunca afirme una "
    "elección que nadie hizo."
)


def trail_for_composition(
    baseline: ComposedBaseline,
    choices: list[CompositionChoice],
    signature: Signature,
    ratified: list[tuple[ComposedZone, ComposedCapability]],
    catalog_mapped: dict[tuple[str, str], bool],
    gating_excluded: dict[tuple[str, str, str], str],
) -> list[AuditEventCreate]:
    """Every entry of one composition, in the order the operator produced it.

    The explicit choices come first, in the order they were made — the trail is a
    decision record, and the order in which an operator worked through the zones is
    part of what it records. The ratifications follow, then the signature that
    closes the baseline.
    """
    entries = [
        _choice(baseline, signature, choice, catalog_mapped, gating_excluded)
        for choice in choices
    ]
    entries += [_ratified(baseline, signature, zone, cap) for zone, cap in ratified]
    entries.append(_signed(baseline, signature, len(choices), len(ratified)))
    return entries


def _choice(
    baseline: ComposedBaseline,
    signature: Signature,
    choice: CompositionChoice,
    catalog_mapped: dict[tuple[str, str], bool],
    gating_excluded: dict[tuple[str, str, str], str],
) -> AuditEventCreate:
    capability = baseline.zone(choice.zone_id).capability(choice.capability_id)
    origin = _origin(choice, catalog_mapped)
    excluded = (
        gating_excluded.get((choice.zone_id, choice.capability_id, choice.control_id))
        if choice.control_id is not None
        else None
    )
    return _event(
        baseline,
        signature,
        CHOICE_EVENTS[choice.kind],
        AuditStage.COMPOSITION,
        decision=_choice_decision(choice, capability),
        rationale=f"{choice.rationale} {_choice_note(choice, capability, origin, excluded)}",
        zone_id=choice.zone_id,
        capability_id=choice.capability_id,
        control_id=choice.control_id,
        payload={
            "kind": choice.kind.value,
            "capability_name": capability.capability_name,
            "tier": capability.tier.value,
            "gating_status": capability.status.value,
            "outstanding": capability.outstanding,
            "origin": origin.value if origin is not None else None,
            "gating_excluded": excluded,
            "explanations_digest": choice.explanations_digest,
        },
    )


def _ratified(
    baseline: ComposedBaseline,
    signature: Signature,
    zone: ComposedZone,
    capability: ComposedCapability,
) -> AuditEventCreate:
    controls = ", ".join(capability.ratified_control_ids) or "sin mecanismo en la capa del activo"
    return _event(
        baseline,
        signature,
        AuditEventType.MECHANISM_RATIFIED,
        AuditStage.COMPOSITION,
        decision=(
            f"Ratificado el mecanismo retenido para «{capability.capability_name}» en "
            f"{zone.zone_id}: {controls}"
        ),
        rationale=(
            f"{signature.rationale} {RATIFICATION_NOTE} Estado del gating: "
            f"{say(capability.status)}; el mandato no figuraba entre los pendientes de la zona, "
            "así que el motor lo daba por cubierto y la firma lo asume."
        ),
        zone_id=zone.zone_id,
        capability_id=capability.capability_id,
        payload={
            "capability_name": capability.capability_name,
            "tier": capability.tier.value,
            "gating_status": capability.status.value,
            "ratified_control_ids": capability.ratified_control_ids,
        },
    )


def _signed(
    baseline: ComposedBaseline, signature: Signature, choices: int, ratified: int
) -> AuditEventCreate:
    mandates = {
        zone.zone_id: zone.outstanding_capability_ids
        for zone in baseline.zones
        if zone.outstanding_capability_ids
    }
    return _event(
        baseline,
        signature,
        AuditEventType.BASELINE_SIGNED,
        AuditStage.SIGNATURE,
        decision=(
            f"Línea base {baseline.baseline_id} firmada por {signature.operator} sobre el perfil "
            f"{baseline.profile_id} ({len(baseline.zones)} zona(s))"
        ),
        rationale=(
            f"{signature.rationale} Se verificó el bloque obligatorio antes de firmar: ningún "
            "mandato de ninguna zona queda abierto, y cada capacidad obligatoria lleva una "
            "entrada con nombre — elegida, compensada, aceptada como hueco o ratificada. La firma "
            "se ancla a la ejecución del motor que la originó y a las versiones de catálogo y "
            "reglas que la gobernaron: la misma firma sobre otro catálogo sería otra línea base."
        ),
        payload={
            "profile_name": baseline.profile_name,
            "zones": [zone.zone_id for zone in baseline.zones],
            "tier_0_complete": baseline.tier_0_complete,
            "closed_mandates": mandates,
            "human_choices": choices,
            "ratified_mandates": ratified,
        },
    )


def _event(
    baseline: ComposedBaseline,
    signature: Signature,
    event_type: AuditEventType,
    stage: AuditStage,
    *,
    decision: str,
    rationale: str,
    zone_id: str | None = None,
    capability_id: str | None = None,
    control_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> AuditEventCreate:
    return AuditEventCreate(
        actor=AuditActor.HUMAN,
        actor_ref=signature.operator,
        stage=stage,
        event_type=event_type,
        run_id=baseline.run_id,
        baseline_id=baseline.baseline_id,
        profile_id=baseline.profile_id,
        zone_id=zone_id,
        capability_id=capability_id,
        control_id=control_id,
        decision=decision,
        rationale=rationale,
        versions=baseline.versions,
        payload=payload or {},
    )


# --- the sentences the operator's entries read as ------------------------------


def _choice_decision(choice: CompositionChoice, capability: ComposedCapability) -> str:
    name = capability.capability_name
    where = f"«{name}» en {choice.zone_id}"
    if choice.kind is ChoiceKind.OPTION_SELECTED:
        return f"Seleccionado {choice.control_id} para {where}"
    if choice.kind is ChoiceKind.OPTION_REJECTED:
        return f"Descartado {choice.control_id} para {where}"
    if choice.kind is ChoiceKind.COMPENSATORY_DECLARED:
        return f"Declarado {choice.control_id} como control compensatorio de {where}"
    return f"Aceptado el hueco de {where} sin mecanismo en la capa del activo"


def _choice_note(
    choice: CompositionChoice,
    capability: ComposedCapability,
    origin: SelectionOrigin | None,
    excluded: str | None,
) -> str:
    mandatory = capability.tier is PriorityTier.TIER_0
    note = (
        "Decisión del humano sobre un mandato del SL-objetivo de la zona: "
        if mandatory
        else "Decisión del humano sobre una capacidad discrecional: "
    )
    note += (
        "el motor ofrece opciones equivalentes y no elige ninguna; la elección y su "
        "justificación son de quien firma."
    )
    if origin is SelectionOrigin.ADOPTED_SUGGESTION:
        note += (
            f" {choice.control_id} no está mapeado a esta capacidad en el catálogo: es una "
            "sugerencia de la recuperación que el humano adopta. Se registra como adopción y no "
            "como mapeo — una distancia entre vectores no se convierte en evidencia autorizada "
            "porque alguien esté de acuerdo con ella; lo que la hace admisible es esta razón "
            "escrita."
        )
    if excluded is not None:
        note += (
            f" Atención: el gating había excluido {choice.control_id} de esta capacidad por "
            f"'{excluded}', y el humano decide sobre él de todos modos. La soberanía del operador "
            "incluye contradecir al motor; lo que no incluye es hacerlo en silencio, así que la "
            "excepción queda anotada aquí junto a su razón."
        )
    if capability.outstanding:
        note += (
            " Cierra un mandato que el motor no podía cerrar solo (sin mecanismo aplicable o con "
            "residual declarado)."
        )
    if choice.explanations_digest:
        note += (
            f" Explicaciones en pantalla al decidir: sha256 {choice.explanations_digest}. La "
            "prosa del modelo es presentacional y no decidió nada; se ancla para poder "
            "reconstruir qué se estaba leyendo."
        )
    return note


def _origin(
    choice: CompositionChoice, catalog_mapped: dict[tuple[str, str], bool]
) -> SelectionOrigin | None:
    if choice.control_id is None:
        return None
    mapped = catalog_mapped.get((choice.capability_id, choice.control_id), False)
    return SelectionOrigin.CATALOG_MAPPING if mapped else SelectionOrigin.ADOPTED_SUGGESTION
