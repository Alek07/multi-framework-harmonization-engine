"""Step 2 of the core: conflict resolution. Never "most restrictive wins".

Three situations: overlap (collapse into one capability, options side by side),
granularity 1:N (report coverage weights, flag the residual), real contradiction
(settle by zone context, mark the loser, or hand a safety override to the human).
Resolution is independent of catalog ingestion order.
"""

from __future__ import annotations

from app.catalog.schemas import Capability, MappingType
from app.core.wording import say
from app.engine.rules import Contradiction, ResolutionStrategy, RuleSet
from app.engine.schemas import (
    CandidateOption,
    CandidateStatus,
    CapabilityGap,
    CapabilityResolution,
    Conflict,
    ConflictType,
    GapKind,
    ResolutionMethod,
    ZoneContext,
)

CONTEXTUAL_OPTION_NOTE = (
    "Overlay contextual por jurisdicción: obligación aplicable, no mecanismo de cobertura."
)


def resolve_capability(
    capability: Capability, options: list[CandidateOption], rules: RuleSet, zone: ZoneContext
) -> CapabilityResolution:
    """Resolve one capability in one zone: mark statuses, record conflicts, flag the gap."""
    for option in options:
        if option.mapping_type is MappingType.CONTEXTUAL:
            option.status_reason = CONTEXTUAL_OPTION_NOTE

    conflicts = _resolve_contradictions(capability, options, rules, zone)
    conflicts.extend(_detect_overlap(capability, options, zone))
    conflicts.extend(_detect_granularity(capability, options, zone))

    effective = _effective(options)
    coverage = max((o.coverage_weight for o in effective), default=0.0)
    has_full_mechanism = any(o.mapping_type is MappingType.TOTAL for o in effective)

    return CapabilityResolution(
        capability=capability,
        zone_id=zone.zone_id,
        options=options,
        coverage=coverage,
        has_full_mechanism=has_full_mechanism,
        conflicts=conflicts,
        gap=_gap(capability, options, effective, coverage, has_full_mechanism, zone),
    )


def _effective(options: list[CandidateOption]) -> list[CandidateOption]:
    """Options that count as coverage: not superseded and not a contextual overlay.

    A contested option still counts: the safety override hands the choice to the
    human, it does not remove the mechanism.
    """
    return [
        o
        for o in options
        if o.status is not CandidateStatus.SUPERSEDED
        and o.mapping_type is not MappingType.CONTEXTUAL
    ]


def _resolve_contradictions(
    capability: Capability, options: list[CandidateOption], rules: RuleSet, zone: ZoneContext
) -> list[Conflict]:
    conflicts: list[Conflict] = []
    by_id = {o.control_id: o for o in options}

    for rule in rules.contradictions_for(capability.id, zone.domain, zone.safety_relevant):
        involved = [by_id[cid] for cid in sorted(rule.control_ids) if cid in by_id]
        if len(involved) < 2:
            # Declared but not materialised in this catalog: no conflict to resolve.
            continue
        if rule.resolution is ResolutionStrategy.SAFETY_OVERRIDE:
            conflicts.append(_apply_safety_override(rule, involved, zone))
        else:
            conflicts.append(_apply_framework_precedence(rule, involved, rules, zone))
    return conflicts


def _apply_framework_precedence(
    rule: Contradiction, involved: list[CandidateOption], rules: RuleSet, zone: ZoneContext
) -> Conflict:
    """The zone's context decides which mechanism prevails — not its strength."""
    prevailing = min(
        involved,
        key=lambda o: (rules.precedence_index(zone.domain, o.framework), o.control_id),
    )
    superseded = [o for o in involved if o is not prevailing]
    superseded_official = ", ".join(sorted(o.control.official_id for o in superseded))
    for option in superseded:
        option.status = CandidateStatus.SUPERSEDED
        option.rule_id = rule.id
        option.status_reason = (
            f"No prevalece en la zona {zone.zone_id} (dominio {say(zone.domain)}): "
            f"la precedencia declarada sitúa {prevailing.framework.value} por delante de "
            f"{option.framework.value}. Se mantiene visible como alternativa descartada, "
            "no se elimina."
        )
    prevailing.rule_id = rule.id
    prevailing.status_reason = (
        f"Prevalece en la zona {zone.zone_id} por precedencia de contexto "
        f"({say(zone.domain)}), no por ser el control más exigente."
    )

    return Conflict(
        id=f"CONF-{zone.zone_id}-{rule.id}",
        conflict_type=ConflictType.CONTRADICTION,
        capability_id=rule.capability_id,
        zone_id=zone.zone_id,
        control_ids=[o.control_id for o in involved],
        method=ResolutionMethod.FRAMEWORK_PRECEDENCE,
        prevailing_control_ids=[prevailing.control_id],
        superseded_control_ids=sorted(o.control_id for o in superseded),
        requires_human_decision=False,
        rationale=(
            f"{rule.rationale} Resolución en {zone.zone_id}: prevalece "
            f"{prevailing.control.official_id} ({prevailing.framework.value}); "
            f"queda marcado como descartado {superseded_official}."
        ),
        rule_id=rule.id,
    )


def _apply_safety_override(
    rule: Contradiction, involved: list[CandidateOption], zone: ZoneContext
) -> Conflict:
    """OT safety override: the engine surfaces the conflict, the human settles it."""
    for option in involved:
        option.status = CandidateStatus.CONTESTED
        option.rule_id = rule.id
        option.status_reason = (
            f"Conflicto real en la zona {zone.zone_id}: el mecanismo no puede impedir la "
            "actuación del operador en emergencia. El motor no elige; la decisión es del humano."
        )

    return Conflict(
        id=f"CONF-{zone.zone_id}-{rule.id}",
        conflict_type=ConflictType.CONTRADICTION,
        capability_id=rule.capability_id,
        zone_id=zone.zone_id,
        control_ids=[o.control_id for o in involved],
        method=ResolutionMethod.SAFETY_OVERRIDE,
        prevailing_control_ids=[],
        superseded_control_ids=[],
        requires_human_decision=True,
        rationale=(
            f"{rule.rationale} La capacidad sigue siendo exigida en {zone.zone_id}: "
            "lo que se expone al humano es la elección del mecanismo, no su omisión."
        ),
        rule_id=rule.id,
    )


def _detect_overlap(
    capability: Capability, options: list[CandidateOption], zone: ZoneContext
) -> list[Conflict]:
    """Several complete mechanisms for the same outcome -> collapse into one capability."""
    full = [
        o
        for o in _effective(options)
        if o.mapping_type is MappingType.TOTAL
    ]
    if len(full) < 2:
        return []

    frameworks = sorted({o.framework.value for o in full})
    return [
        Conflict(
            id=f"CONF-{zone.zone_id}-{capability.id}-OVERLAP",
            conflict_type=ConflictType.OVERLAP,
            capability_id=capability.id,
            zone_id=zone.zone_id,
            control_ids=sorted(o.control_id for o in full),
            method=ResolutionMethod.COLLAPSED,
            prevailing_control_ids=sorted(o.control_id for o in full),
            superseded_control_ids=[],
            requires_human_decision=False,
            rationale=(
                f"{len(full)} controles de {len(frameworks)} marcos ({', '.join(frameworks)}) "
                f"cubren por completo la misma capacidad. Se colapsan en un único requisito con "
                "opciones equivalentes lado a lado: no se duplica la exigencia ni se descarta "
                "ninguna opción; la elección es del humano."
            ),
        )
    ]


def _detect_granularity(
    capability: Capability, options: list[CandidateOption], zone: ZoneContext
) -> list[Conflict]:
    """1:N granularity -> report coverage weights and let the gap surface."""
    pieces = [
        o
        for o in _effective(options)
        if o.mapping_type in (MappingType.PARTIAL, MappingType.COMPENSATORY)
    ]
    if not pieces:
        return []

    detail = ", ".join(
        f"{o.control.official_id} (mapeo {say(o.mapping_type)}, cobertura {o.coverage_weight})"
        for o in sorted(pieces, key=lambda o: o.control_id)
    )
    return [
        Conflict(
            id=f"CONF-{zone.zone_id}-{capability.id}-GRANULARITY",
            conflict_type=ConflictType.GRANULARITY,
            capability_id=capability.id,
            zone_id=zone.zone_id,
            control_ids=sorted(o.control_id for o in pieces),
            method=ResolutionMethod.COVERAGE_WEIGHTS,
            prevailing_control_ids=[],
            superseded_control_ids=[],
            requires_human_decision=False,
            rationale=(
                f"Granularidad 1:N: la capacidad se alcanza por piezas — {detail}. "
                "Los pesos se reportan como evidencia; el residuo se señala como hueco explícito. "
                "Las coberturas parciales no se suman entre sí: sumarlas fabricaría una cobertura "
                "total inexistente."
            ),
        )
    ]


def _gap(
    capability: Capability,
    options: list[CandidateOption],
    effective: list[CandidateOption],
    coverage: float,
    has_full_mechanism: bool,
    zone: ZoneContext,
) -> CapabilityGap | None:
    """Flag what is missing. A capability is never quietly considered covered."""
    residual = round(1.0 - coverage, 6)

    if not options:
        kind, rationale = (
            GapKind.NO_CANDIDATE,
            "Ningún control del catálogo cubre esta capacidad: hueco explícito, no omisión.",
        )
    elif not effective:
        kind, rationale = (
            GapKind.NO_EFFECTIVE_MECHANISM,
            "Todos los candidatos son overlays contextuales o quedaron descartados por "
            "precedencia: la capacidad sigue exigida y sin mecanismo efectivo en esta zona.",
        )
    elif not has_full_mechanism:
        kind, rationale = (
            GapKind.PARTIAL_ONLY,
            f"Sin mecanismo de cobertura total: la mejor pieza cubre {coverage} y queda un "
            f"residuo de {residual} que ningún control del catálogo cierra.",
        )
    elif residual > 0:
        kind, rationale = (
            GapKind.RESIDUAL_COVERAGE,
            f"El mejor mecanismo total cubre {coverage}: queda un residuo declarado de {residual} "
            "(el catálogo no afirma cobertura completa).",
        )
    else:
        return None

    return CapabilityGap(
        capability_id=capability.id,
        zone_id=zone.zone_id,
        kind=kind,
        coverage=coverage,
        residual=residual,
        rationale=rationale,
    )
