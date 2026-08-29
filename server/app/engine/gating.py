"""UCM-9 - Step 3 of the core: deterministic gating by asset profile.

Mapping and conflict resolution answer *which mechanisms exist* for a capability.
Gating answers a different question: *which of them this asset can actually
host*. A controller with no general-purpose OS cannot run a resident antimalware
agent; an enterprise remediation cadence is not executable on equipment that
needs an operating window to stop. Saying so is the engineering judgement the
baseline needs — and hiding it would be the omission the TFM measures.

Three outcomes, and only three, for a control without an equivalent here:

* **No aplica** — the control's technical premise does not exist in this asset.
  A justified exclusion: a *deliverable* of the baseline, not a gap.
* **Objetivo sin mecanismo** — the objective still stands, the asset cannot host
  the mechanism. A compensatory control is owed, and the rule names it.
* **Ámbito equivocado** — not a zone-layer mechanism at all (governance, people,
  legal obligation). Deferred to the organizational layer, never deleted.

Golden rule, enforced here and in the schema: gating removes **mechanisms**,
never required **capabilities**, and never silently. `CapabilityGating.required`
cannot be False; every exclusion carries its rule, the premises read from the
profile and a written justification; and a capability left without a mechanism
becomes an explicit gap instead of quietly disappearing.

Because applicability is read from the zone — both its domain/safety reading and
its own `TechNature` premises — the same catalog produces different baselines for
different zones, which is the whole point of composing one.
"""

from __future__ import annotations

from app.catalog.schemas import MappingType
from app.engine.applicability import applicability_decision
from app.engine.gating_rules import GatingRule, GatingRules
from app.engine.schemas import (
    CandidateOption,
    CandidateStatus,
    CapabilityGap,
    CapabilityGating,
    CapabilityResolution,
    CapabilityStatus,
    GapKind,
    GatingDecision,
    GatingOutcome,
    ZoneContext,
    ZoneGating,
    ZoneResolution,
)

# What each outcome means for the mechanism that leaves — spelled out in every
# decision, so no exclusion can ever be read as a silent drop.
OUTCOME_NOTE: dict[GatingOutcome, str] = {
    GatingOutcome.NOT_APPLICABLE: (
        "Exclusión justificada: el mecanismo no tiene premisa en este activo. Es un entregable "
        "de la baseline (lo que se dejó fuera y por qué), no un hueco."
    ),
    GatingOutcome.OBJECTIVE_WITHOUT_MECHANISM: (
        "El objetivo sigue exigido en la zona: lo que falta es el mecanismo, y queda pendiente "
        "de un control compensatorio declarado."
    ),
    GatingOutcome.WRONG_SCOPE: (
        "El requisito no se elimina: cambia de capa. Sigue exigido y se acredita fuera del "
        "activo, con su rastro en el registro."
    ),
}

# Mechanisms that cover the capability directly. A compensatory mapping is a
# fallback route, not a mechanism: keeping them apart is what lets the engine
# say "objective without mechanism" instead of pretending the outcome is met.
MECHANISM_TYPES = (MappingType.TOTAL, MappingType.PARTIAL)


def gate_capability(
    resolution: CapabilityResolution,
    zone: ZoneContext,
    rules: GatingRules,
) -> CapabilityGating:
    """Gate one capability in one zone: exclude mechanisms, never the requirement."""
    capability_id = resolution.capability.id
    excluded = [_decision(option, capability_id, zone, rules) for option in resolution.options]
    decisions = [d for d in excluded if d is not None]
    excluded_ids = {d.control_id for d in decisions}

    # A superseded option was already set aside by precedence (UCM-8); a contextual
    # overlay was never a mechanism. Neither is available to cover the capability.
    available = [
        o
        for o in resolution.options
        if o.status is not CandidateStatus.SUPERSEDED
        and o.mapping_type is not MappingType.CONTEXTUAL
        and o.control_id not in excluded_ids
    ]
    mechanisms = [o for o in available if o.mapping_type in MECHANISM_TYPES]
    compensatory = [o for o in available if o.mapping_type is MappingType.COMPENSATORY]
    coverage = max((o.coverage_weight for o in available), default=0.0)

    status, deferred_to = _status(resolution.options, mechanisms, compensatory, decisions)
    gap = _gap(capability_id, zone, status, resolution.options, available, coverage)

    return CapabilityGating(
        capability_id=capability_id,
        zone_id=zone.zone_id,
        status=status,
        retained_control_ids=sorted(o.control_id for o in mechanisms),
        compensatory_control_ids=sorted(o.control_id for o in compensatory),
        excluded=sorted(decisions, key=lambda d: d.control_id),
        coverage=coverage,
        coverage_before_gating=resolution.coverage,
        deferred_to=deferred_to,
        gap=gap,
        rationale=_rationale(status, zone, mechanisms, compensatory, decisions, deferred_to),
    )


def gate_zone(resolution: ZoneResolution, rules: GatingRules) -> ZoneGating:
    """Gate every capability of the catalog in a zone — none is dropped from the list.

    The premises come from `resolution.zone.nature`, which is this zone's own
    reading: a hybrid asset gates its jetty controller and its control room off
    different premises, which is why nature is not an asset-wide field.
    """
    return ZoneGating(
        zone=resolution.zone,
        capabilities=[
            gate_capability(capability, resolution.zone, rules)
            for capability in resolution.capabilities
        ],
    )


def _decision(
    option: CandidateOption,
    capability_id: str,
    zone: ZoneContext,
    rules: GatingRules,
) -> GatingDecision | None:
    """Apply the declared rules to one candidate. No rule fires -> it stays.

    Gating is evaluated on every candidate, including one already superseded by
    precedence: "this mechanism has no premise here" and "this mechanism does not
    prevail here" are different answers and the human deserves both.
    """
    matched = rules.rules_for(option.control_id, zone)

    # Sectoral applicability (UCM-47) is prior to every rule; a matched rule is kept as context.
    outside_scope = applicability_decision(
        option.control, capability_id, zone, [r.id for r in matched]
    )
    if outside_scope is not None:
        return outside_scope

    if not matched:
        return None

    rule, *rest = matched
    return GatingDecision(
        zone_id=zone.zone_id,
        capability_id=capability_id,
        control_id=option.control_id,
        outcome=rule.outcome,
        rule_id=rule.id,
        rationale=_decision_rationale(rule, zone),
        evidence=rule.applies_when.evidence(zone),
        compensation=rule.compensation,
        deferred_to=rule.deferred_to,
        also_matched_rule_ids=[r.id for r in rest],
    )


def _decision_rationale(rule: GatingRule, zone: ZoneContext) -> str:
    return (
        f"{rule.rationale} Gating en la zona {zone.zone_id} por la regla {rule.id}. "
        f"{OUTCOME_NOTE[rule.outcome]}"
    )


def _status(
    options: list[CandidateOption],
    mechanisms: list[CandidateOption],
    compensatory: list[CandidateOption],
    decisions: list[GatingDecision],
) -> tuple[CapabilityStatus, str | None]:
    """Where the capability stands after gating. It is never "not required"."""
    if mechanisms:
        return CapabilityStatus.COVERED_BY_MECHANISM, None
    if compensatory:
        return CapabilityStatus.COMPENSATORY_REQUIRED, None

    # Deferred only when *every* mechanism the catalog offers for this capability
    # was ruled out of scope: anything else leaves an asset-layer requirement open.
    candidates = [o for o in options if o.mapping_type is not MappingType.CONTEXTUAL]
    deferred = {d.control_id for d in decisions if d.outcome is GatingOutcome.WRONG_SCOPE}
    if candidates and all(o.control_id in deferred for o in candidates):
        layers = sorted({d.deferred_to for d in decisions if d.deferred_to})
        return CapabilityStatus.DEFERRED_TO_ORGANIZATIONAL_LAYER, " · ".join(layers)
    return CapabilityStatus.COMPENSATORY_REQUIRED, None


def _gap(
    capability_id: str,
    zone: ZoneContext,
    status: CapabilityStatus,
    options: list[CandidateOption],
    available: list[CandidateOption],
    coverage: float,
) -> CapabilityGap | None:
    """What gating leaves open at the asset layer. A deferral is not a hole here."""
    if status is CapabilityStatus.DEFERRED_TO_ORGANIZATIONAL_LAYER:
        return None

    residual = round(1.0 - coverage, 6)
    if not options:
        kind, rationale = (
            GapKind.NO_CANDIDATE,
            "Ningún control del catálogo cubre esta capacidad: hueco explícito, no omisión.",
        )
    elif not available:
        kind, rationale = (
            GapKind.NO_EFFECTIVE_MECHANISM,
            "Tras el gating no queda ningún mecanismo aplicable en la zona. La capacidad sigue "
            "exigida: el humano debe componer un control compensatorio.",
        )
    elif not any(o.mapping_type is MappingType.TOTAL for o in available):
        kind, rationale = (
            GapKind.PARTIAL_ONLY,
            f"Sin mecanismo de cobertura total aplicable en la zona: lo que queda tras el gating "
            f"cubre {coverage} y deja un residuo de {residual}.",
        )
    elif residual > 0:
        kind, rationale = (
            GapKind.RESIDUAL_COVERAGE,
            f"El mejor mecanismo aplicable cubre {coverage}: queda un residuo declarado de "
            f"{residual} (el catálogo no afirma cobertura completa).",
        )
    else:
        return None

    return CapabilityGap(
        capability_id=capability_id,
        zone_id=zone.zone_id,
        kind=kind,
        coverage=coverage,
        residual=residual,
        rationale=rationale,
    )


def _rationale(
    status: CapabilityStatus,
    zone: ZoneContext,
    mechanisms: list[CandidateOption],
    compensatory: list[CandidateOption],
    decisions: list[GatingDecision],
    deferred_to: str | None,
) -> str:
    """Every capability says out loud what gating did to it — including nothing."""
    excluded_note = (
        f"Se excluyeron {len(decisions)} mecanismo(s) con regla y justificación."
        if decisions
        else "El gating no excluyó ningún mecanismo."
    )
    if status is CapabilityStatus.COVERED_BY_MECHANISM:
        return (
            f"Capacidad exigida en {zone.zone_id} y cubierta por {len(mechanisms)} mecanismo(s) "
            f"aplicable(s) tras el gating. {excluded_note}"
        )
    if status is CapabilityStatus.DEFERRED_TO_ORGANIZATIONAL_LAYER:
        return (
            f"Capacidad exigida en {zone.zone_id} cuyo cumplimiento no se ejerce en el activo: "
            f"todos sus mecanismos son de ámbito equivocado y se difieren a {deferred_to}. "
            "No se elimina: cambia de capa y queda en el registro."
        )
    if compensatory:
        return (
            f"Capacidad exigida en {zone.zone_id} sin mecanismo directo aplicable: se sostiene "
            f"sobre {len(compensatory)} control(es) compensatorio(s) del catálogo, con el "
            f"residuo declarado. {excluded_note}"
        )
    return (
        f"Capacidad exigida en {zone.zone_id} sin mecanismo aplicable en el catálogo: exige un "
        f"control compensatorio que el humano debe componer. {excluded_note}"
    )
