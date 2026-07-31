"""UCM-11 - Derivation of the log from the deterministic core's output.

Pure and deterministic: the same core output always yields the same entries, in
the same order, with the same texts. Only `sequence`, `recorded_at` and the
hashes come from the ledger (`repository.py`) — everything a reader needs to
understand *why* is computed here, from what the engine already decided.

The trail follows the pipeline: mapping → conflict resolution → gating →
prioritisation, and it closes the run. Two rules shape what gets written:

* **Nothing silent.** Every capability of the catalog leaves a mark in every
  zone (`capability_mapped`), whether it has candidates or is an explicit gap,
  and each stage closes with a `stage_completed` that names the capabilities it
  accounted for. The 0-silent-omissions invariant is therefore measurable *on the
  log itself*, not only on the engine's return value.
* **Nothing anonymous.** Each entry carries the actor (always `engine` here — the
  human's entries come from `service.record_human_decision`), the component that
  decided (`actor_ref`), the declared rule that fired (`rule_id`) and the versions
  of the inputs that governed it.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.assets.schemas import AssetProfile
from app.audit.schemas import AuditActor, AuditEventCreate, AuditEventType, AuditStage
from app.engine.schemas import (
    CapabilityGap,
    CapabilityGating,
    CapabilityPriority,
    CapabilityResolution,
    CapabilityStatus,
    Conflict,
    GatingDecision,
    PriorityTier,
    ProfileGating,
    ProfilePrioritization,
    ProfileResolution,
    ZoneGating,
    ZonePrioritization,
    ZoneResolution,
)

# Which component of the core authored the decision. The stage is not decoration:
# it is the answer to "who inside the engine decided this, and under which step".
ACTOR_REFS: dict[AuditStage, str] = {
    AuditStage.RUN: "engine.service",
    AuditStage.MAPPING: "engine.mapping",
    AuditStage.CONFLICT_RESOLUTION: "engine.conflicts",
    AuditStage.GATING: "engine.gating",
    AuditStage.PRIORITIZATION: "engine.prioritization",
    # The RAG pass (UCM-13) is engine-authored too: the retriever offers, it does
    # not decide, so its entries are the engine's — never the model's.
    AuditStage.RETRIEVAL: "engine.retrieval",
}


class _Trail:
    """Accumulates the entries of one run, filling in what is constant for it."""

    def __init__(self, run_id: UUID, profile_id: str, versions: dict[str, str]) -> None:
        self.run_id = run_id
        self.profile_id = profile_id
        self.versions = versions
        self.entries: list[AuditEventCreate] = []
        # Capability names, so the log reads like a decision record and not like
        # a list of identifiers. Filled from the resolution as it is walked.
        self.names: dict[str, str] = {}

    def add(
        self,
        stage: AuditStage,
        event_type: AuditEventType,
        decision: str,
        rationale: str,
        *,
        zone_id: str | None = None,
        capability_id: str | None = None,
        control_id: str | None = None,
        rule_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.entries.append(
            AuditEventCreate(
                actor=AuditActor.ENGINE,
                actor_ref=ACTOR_REFS[stage],
                stage=stage,
                event_type=event_type,
                run_id=self.run_id,
                profile_id=self.profile_id,
                zone_id=zone_id,
                capability_id=capability_id,
                control_id=control_id,
                rule_id=rule_id,
                decision=decision,
                rationale=rationale,
                versions=self.versions,
                payload=payload or {},
            )
        )

    def label(self, capability_id: str) -> str:
        return self.names.get(capability_id, capability_id)


def trail_for_core_run(
    profile: AssetProfile,
    resolution: ProfileResolution,
    gating: ProfileGating,
    prioritization: ProfilePrioritization,
    run_id: UUID,
) -> list[AuditEventCreate]:
    """Every decision of one core run, in pipeline order, ready to be appended."""
    _check_one_run(profile, resolution, gating, prioritization)

    trail = _Trail(run_id, profile.id, _versions(prioritization))
    _run_started(trail, profile, resolution)
    for resolved in resolution.zones:
        _mapping(trail, resolved)
    for resolved in resolution.zones:
        _conflict_resolution(trail, resolved)
    for gated in gating.zones:
        _gating(trail, gated, resolution.zone(gated.zone.zone_id))
    for prioritized in prioritization.zones:
        _prioritization(trail, prioritized)
    _run_completed(trail, prioritization)
    return trail.entries


# --- steps 1-2: mapping and conflict resolution (UCM-8) -----------------------


def _mapping(trail: _Trail, zone: ZoneResolution) -> None:
    context = zone.zone
    trail.add(
        AuditStage.MAPPING,
        AuditEventType.ZONE_DERIVED,
        f"Zona {context.zone_id}: dominio {context.domain.value}, "
        f"SL-objetivo {context.target_sl}",
        f"{context.derivation} La lectura de la zona es determinista y gobierna dos cosas: la "
        f"precedencia de marcos en los contradictorios y el bloque obligatorio por SL-objetivo.",
        zone_id=context.zone_id,
        payload=context.model_dump(mode="json"),
    )

    for capability in zone.capabilities:
        trail.names[capability.capability.id] = capability.capability.name
        _capability_mapped(trail, capability)

    with_candidates = [c.capability.id for c in zone.capabilities if c.options]
    trail.add(
        AuditStage.MAPPING,
        AuditEventType.STAGE_COMPLETED,
        f"Mapeo completado en {context.zone_id}: {len(zone.capabilities)} capacidad(es) "
        f"del catálogo",
        "Todas las capacidades del catálogo quedan registradas en la zona, con sus candidatos o "
        "como hueco explícito. Ninguna se descarta ni se restringe: el RAG (M2) solo podrá "
        "ampliar esta cobertura, nunca recortarla.",
        zone_id=context.zone_id,
        payload={
            "capabilities": len(zone.capabilities),
            "with_candidates": len(with_candidates),
            "without_candidates": len(zone.capabilities) - len(with_candidates),
            "capability_ids": [c.capability.id for c in zone.capabilities],
        },
    )


def _capability_mapped(trail: _Trail, capability: CapabilityResolution) -> None:
    name = capability.capability.name
    zone_id = capability.zone_id
    if capability.options:
        decision = f"{len(capability.options)} candidato(s) para «{name}» en {zone_id}"
        rationale = (
            f"Cobertura resultante {capability.coverage} "
            f"({'con' if capability.has_full_mechanism else 'sin'} mecanismo de cobertura total). "
            "Se registran todos los candidatos con su marco, jurisdicción, tipo de mapeo y "
            "procedencia: el motor no filtra ni ordena aquí, ofrece."
        )
    else:
        decision = f"Ningún candidato del catálogo para «{name}» en {zone_id}"
        rationale = (
            "El catálogo no ofrece ningún control para esta capacidad en la zona. Se registra "
            "como hueco explícito en el paso siguiente: la capacidad sigue exigida."
        )

    trail.add(
        AuditStage.MAPPING,
        AuditEventType.CAPABILITY_MAPPED,
        decision,
        rationale,
        zone_id=zone_id,
        capability_id=capability.capability.id,
        payload={
            "capability_name": name,
            "coverage": capability.coverage,
            "has_full_mechanism": capability.has_full_mechanism,
            "options": [option.model_dump(mode="json") for option in capability.options],
        },
    )


def _conflict_resolution(trail: _Trail, zone: ZoneResolution) -> None:
    zone_id = zone.zone.zone_id
    for capability in zone.capabilities:
        for conflict in capability.conflicts:
            _conflict(trail, conflict)
        if capability.gap is not None:
            _gap(trail, AuditStage.CONFLICT_RESOLUTION, capability.gap)

    escalated = zone.open_decisions
    trail.add(
        AuditStage.CONFLICT_RESOLUTION,
        AuditEventType.STAGE_COMPLETED,
        f"Resolución de conflictos completada en {zone_id}: {len(zone.conflicts)} conflicto(s), "
        f"{len(escalated)} elevado(s) al humano",
        "La resolución nunca es «gana el más restrictivo»: solapamiento se colapsa, la "
        "granularidad se pondera por cobertura y el contradictorio real se decide por "
        "precedencia de zona — o se eleva al humano cuando el motor no debe decidirlo. Ningún "
        "candidato se elimina: el que no prevalece queda marcado y visible.",
        zone_id=zone_id,
        payload={
            "conflicts": len(zone.conflicts),
            "escalated": len(escalated),
            "escalated_ids": [conflict.id for conflict in escalated],
            "gaps": len(zone.gaps),
            "gap_capability_ids": [gap.capability_id for gap in zone.gaps],
        },
    )


def _conflict(trail: _Trail, conflict: Conflict) -> None:
    label = trail.label(conflict.capability_id)
    if conflict.requires_human_decision:
        event_type = AuditEventType.CONFLICT_ESCALATED
        decision = (
            f"Conflicto {conflict.conflict_type.value} en «{label}» ({conflict.zone_id}) "
            f"elevado al humano"
        )
        note = (
            " El motor no lo resuelve por diseño: es una contradicción real entre marcos y la "
            "elección es soberana del operador (UCM-16)."
        )
    else:
        event_type = AuditEventType.CONFLICT_RESOLVED
        decision = (
            f"Conflicto {conflict.conflict_type.value} en «{label}» ({conflict.zone_id}) "
            f"resuelto por {conflict.method.value}"
        )
        note = (
            " Resolución independiente del orden de ingesta: depende de la regla declarada, no "
            "de cómo se leyó el catálogo."
        )

    trail.add(
        AuditStage.CONFLICT_RESOLUTION,
        event_type,
        decision,
        f"{conflict.rationale}{note}",
        zone_id=conflict.zone_id,
        capability_id=conflict.capability_id,
        rule_id=conflict.rule_id,
        payload=conflict.model_dump(mode="json"),
    )


def _gap(trail: _Trail, stage: AuditStage, gap: CapabilityGap, note: str = "") -> None:
    trail.add(
        stage,
        AuditEventType.GAP_DECLARED,
        f"Hueco {gap.kind.value} en «{trail.label(gap.capability_id)}» ({gap.zone_id}): "
        f"cobertura {gap.coverage}, residuo {gap.residual}",
        f"{gap.rationale}{note} Se declara como hueco explícito y con su residuo: la invariante "
        "medida del TFM es 0 omisiones silenciosas.",
        zone_id=gap.zone_id,
        capability_id=gap.capability_id,
        payload=gap.model_dump(mode="json"),
    )


# --- step 3: gating (UCM-9) ---------------------------------------------------


def _gating(trail: _Trail, zone: ZoneGating, before: ZoneResolution) -> None:
    zone_id = zone.zone.zone_id
    gaps_before = {c.capability.id: c.gap for c in before.capabilities}
    carried_over: list[str] = []

    for capability in zone.capabilities:
        for excluded in capability.excluded:
            _mechanism_excluded(trail, excluded)
        if capability.status is not CapabilityStatus.COVERED_BY_MECHANISM:
            _capability_status(trail, capability)
        if capability.gap is None:
            continue
        if capability.gap == gaps_before.get(capability.capability_id):
            # Already recorded before gating and unchanged by it: re-declaring it
            # would be noise, but it must not look like it went away either.
            carried_over.append(capability.capability_id)
        else:
            _gap(
                trail,
                AuditStage.GATING,
                capability.gap,
                note=" El hueco lo abre o lo agrava el gating de la zona.",
            )

    trail.add(
        AuditStage.GATING,
        AuditEventType.STAGE_COMPLETED,
        f"Gating completado en {zone_id}: {len(zone.decisions)} mecanismo(s) excluido(s) de "
        f"{len(zone.capabilities)} capacidad(es) exigida(s)",
        "El gating quita mecanismos, nunca capacidades exigidas, y nunca en silencio: cada "
        "exclusión lleva regla, premisa observada del perfil y justificación escrita. Las "
        "exclusiones justificadas son un entregable de la baseline; los objetivos sin mecanismo "
        "quedan debiendo un control compensatorio; el ámbito equivocado cambia de capa sin salir "
        "del registro.",
        zone_id=zone_id,
        payload={
            "capabilities": len(zone.capabilities),
            "capability_ids": [c.capability_id for c in zone.capabilities],
            "excluded_mechanisms": len(zone.decisions),
            "justified_exclusions": len(zone.justified_exclusions),
            "compensatory_requirements": len(zone.compensatory_requirements),
            "organizational_deferrals": len(zone.organizational_deferrals),
            "gaps": len(zone.gaps),
            "gaps_carried_over": carried_over,
        },
    )


def _mechanism_excluded(trail: _Trail, excluded: GatingDecision) -> None:
    trail.add(
        AuditStage.GATING,
        AuditEventType.MECHANISM_EXCLUDED,
        f"Mecanismo {excluded.control_id} excluido de "
        f"«{trail.label(excluded.capability_id)}» ({excluded.zone_id}): "
        f"{excluded.outcome.value}",
        excluded.rationale,
        zone_id=excluded.zone_id,
        capability_id=excluded.capability_id,
        control_id=excluded.control_id,
        rule_id=excluded.rule_id,
        payload=excluded.model_dump(mode="json"),
    )


def _capability_status(trail: _Trail, capability: CapabilityGating) -> None:
    trail.add(
        AuditStage.GATING,
        AuditEventType.CAPABILITY_STATUS_SET,
        f"«{trail.label(capability.capability_id)}» en {capability.zone_id}: "
        f"{capability.status.value} — la capacidad sigue exigida",
        capability.rationale,
        zone_id=capability.zone_id,
        capability_id=capability.capability_id,
        payload=capability.model_dump(mode="json"),
    )


# --- step 4: prioritisation (UCM-10) ------------------------------------------


def _prioritization(trail: _Trail, zone: ZonePrioritization) -> None:
    zone_id = zone.zone.zone_id
    for capability in zone.capabilities:
        if capability.tier is PriorityTier.TIER_0:
            _mandate(trail, capability)
        else:
            _priority(trail, capability)
        if capability.outstanding:
            _outstanding(trail, capability)

    trail.add(
        AuditStage.PRIORITIZATION,
        AuditEventType.ROADMAP_PHASED,
        f"Hoja de ruta de {zone_id}: {len(zone.phases)} fase(s)",
        "La fase 0 es el bloque obligatorio por SL-objetivo y no es un ranking: debe estar "
        "completa. Solo el Tier 1 se ordena, con escalas ordinales, orden parcial por "
        "dependencias y coste ordinal — sin cifras inventadas.",
        zone_id=zone_id,
        payload={"phases": [phase.model_dump(mode="json") for phase in zone.phases]},
    )

    trail.add(
        AuditStage.PRIORITIZATION,
        AuditEventType.STAGE_COMPLETED,
        f"Priorización completada en {zone_id}: {len(zone.tier_0)} en Tier 0, "
        f"{len(zone.tier_1)} en Tier 1, {len(zone.outstanding_mandates)} pendiente(s)",
        "Nunca se prioriza todo junto: lo obligatorio por SL-objetivo no compite con lo "
        "discrecional. Lo que el motor no puede dar por cumplido queda listado como pendiente "
        "para que el humano lo cierre antes de firmar.",
        zone_id=zone_id,
        payload={
            "tier_0": [c.capability_id for c in zone.tier_0],
            "tier_1": [c.capability_id for c in zone.tier_1],
            "outstanding": [c.capability_id for c in zone.outstanding_mandates],
            "tier_0_complete": zone.tier_0_complete,
        },
    )


def _mandate(trail: _Trail, capability: CapabilityPriority) -> None:
    trail.add(
        AuditStage.PRIORITIZATION,
        AuditEventType.MANDATE_RECORDED,
        f"«{trail.label(capability.capability_id)}» es Tier 0 en {capability.zone_id} por "
        f"{len(capability.mandates)} mandato(s)",
        f"{capability.rationale} Lo obligatorio no se prioriza: se completa, y por eso su "
        "prioridad ordinal queda deliberadamente vacía.",
        zone_id=capability.zone_id,
        capability_id=capability.capability_id,
        payload=capability.model_dump(mode="json"),
    )


def _priority(trail: _Trail, capability: CapabilityPriority) -> None:
    priority = capability.priority.value if capability.priority is not None else "sin prioridad"
    trail.add(
        AuditStage.PRIORITIZATION,
        AuditEventType.PRIORITY_ASSIGNED,
        f"«{trail.label(capability.capability_id)}» en {capability.zone_id}: Tier 1, "
        f"prioridad {priority}, fase {capability.phase}",
        f"{capability.rationale} Escalas ordinales (beneficio {capability.benefit.value}, coste "
        f"{capability.cost.value}): Gordon-Loeb en espíritu, sin cifras inventadas.",
        zone_id=capability.zone_id,
        capability_id=capability.capability_id,
        payload=capability.model_dump(mode="json"),
    )


def _outstanding(trail: _Trail, capability: CapabilityPriority) -> None:
    trail.add(
        AuditStage.PRIORITIZATION,
        AuditEventType.MANDATE_OUTSTANDING,
        f"Mandato pendiente: «{trail.label(capability.capability_id)}» en {capability.zone_id}",
        f"{capability.rationale} El motor no puede dar por cumplido este mandato: el humano debe "
        "cerrarlo con un mecanismo o con un control compensatorio justificado antes de que "
        "«POST /baseline/compose» acepte la firma.",
        zone_id=capability.zone_id,
        capability_id=capability.capability_id,
        payload=capability.model_dump(mode="json"),
    )


# --- run lifecycle ------------------------------------------------------------


def _run_started(trail: _Trail, profile: AssetProfile, resolution: ProfileResolution) -> None:
    trail.add(
        AuditStage.RUN,
        AuditEventType.RUN_STARTED,
        f"Ejecución del núcleo determinista sobre el perfil {profile.id} "
        f"({len(profile.zones)} zona(s))",
        "Núcleo determinista sin IA: el mismo catálogo, las mismas reglas y el mismo perfil "
        "producen siempre el mismo resultado. Se registran el perfil de entrada y las versiones "
        "de las entradas que gobiernan cada decisión de esta ejecución, para poder reproducirla.",
        payload={
            "profile": profile.model_dump(mode="json"),
            "zones": [zone.zone.zone_id for zone in resolution.zones],
        },
    )


def _run_completed(trail: _Trail, prioritization: ProfilePrioritization) -> None:
    outstanding = [c.capability_id for c in prioritization.outstanding_mandates]
    trail.add(
        AuditStage.RUN,
        AuditEventType.RUN_COMPLETED,
        f"Ejecución completada: {len(prioritization.zones)} zona(s), bloque obligatorio "
        f"{'completo' if prioritization.tier_0_complete else 'incompleto'}",
        "El motor no compone ni firma: entrega opciones equivalentes, conflictos abiertos, "
        "huecos declarados y hoja de ruta por fases para que el humano elija por zona y firme "
        "(UCM-16). Todo lo registrado aquí es la entrada auditable de esa composición.",
        payload={
            "zones": [zone.zone.zone_id for zone in prioritization.zones],
            "tier_0_complete": prioritization.tier_0_complete,
            "outstanding_mandates": outstanding,
        },
    )


# --- consistency of the run ---------------------------------------------------


def _versions(prioritization: ProfilePrioritization) -> dict[str, str]:
    """Provenance of every decision in the run: which versioned inputs governed it."""
    return {
        "catalog": prioritization.catalog_version,
        "rules": prioritization.rules_version,
        "gating": prioritization.gating_version,
        "prioritization": prioritization.prioritization_version,
    }


def _check_one_run(
    profile: AssetProfile,
    resolution: ProfileResolution,
    gating: ProfileGating,
    prioritization: ProfilePrioritization,
) -> None:
    """Refuse to log a trail stitched together from different runs.

    The core chains its steps on purpose (gating decorates the resolution,
    prioritisation decorates the gating). A log built from mismatched pieces would
    be a plausible-looking lie, so it is rejected instead of recorded.
    """
    profile_ids = {profile.id, resolution.profile_id, gating.profile_id, prioritization.profile_id}
    if len(profile_ids) > 1:
        raise ValueError(f"the run mixes asset profiles: {sorted(profile_ids)}")

    versions = {
        (r.catalog_version, r.rules_version) for r in (resolution, gating, prioritization)
    }
    if len(versions) > 1:
        raise ValueError(f"the run mixes catalog/rules versions: {sorted(versions)}")

    gating_versions = {gating.gating_version, prioritization.gating_version}
    if len(gating_versions) > 1:
        raise ValueError(f"the run mixes gating versions: {sorted(gating_versions)}")

    zones = [
        [zone.zone.zone_id for zone in resolution.zones],
        [zone.zone.zone_id for zone in gating.zones],
        [zone.zone.zone_id for zone in prioritization.zones],
        [zone.id for zone in profile.zones],
    ]
    if any(zone_ids != zones[0] for zone_ids in zones):
        raise ValueError(f"the run mixes zones: {zones}")
