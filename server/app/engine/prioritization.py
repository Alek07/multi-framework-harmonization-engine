"""UCM-10 - Step 4 of the core: prioritisation and phased roadmap.

Mapping says which mechanisms exist, conflict resolution which one prevails,
gating which ones this asset can host. Prioritisation answers the operator's
last question — *and now, in what order?* — without ever ranking everything
together, because ranking everything together is what turns a baseline into a
wish list.

Two tiers, and they are not comparable:

* **Tier 0** — mandatory at the zone's SL-target (an IEC 62443-3-3 SR required
  at or below the SL the zone declares for its foundational requirement) or by
  a legal obligation. It is *not prioritised*: `priority` is null by contract
  and every item lands in phase 0. A Tier 0 capability that gating left without
  an applicable mechanism, or with a declared residual, is reported as
  **outstanding** — that list is exactly what `POST /baseline/compose` has to
  find empty before signing (UCM-16).
* **Tier 1** — discretionary. This is the only thing the engine orders, and it
  orders it ordinally: coverage and leverage on one side, declared cost on the
  other, resolved through a declared table.

Gordon-Loeb in spirit, ordinal scales in practice: the engine compares risk
reduction against cost, but it does not own the probabilities or the euros that
a real Gordon-Loeb calculation needs, so it does not pretend to. It says "alta
frente a media" and shows the table that turned the pair into a phase. Saying so
out loud is the rigour; inventing a number would be the fiction.

The CIS Implementation Groups are reused as what they are — an IT prioritisation
already done by someone else — and only where they belong: they order inside
IT/hybrid zones and stay informational in OT ones.

Dependencies are a **partial order**, not a ranking: a capability is never
scheduled before its prerequisite. One asymmetry is deliberate: the lift never
moves a Tier 0 item, because a mandate cannot be deferred by a discretionary
prerequisite. The relation stays visible in `depends_on`/`unlocks` so the human
sees the sequencing the engine refused to impose.

Nothing is dropped here either: every capability of the catalog appears in
exactly one phase of every zone, with its tier, its evidence and its rationale.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.assets.schemas import ConsequenceScale
from app.catalog.schemas import Catalog, ControlType, Framework, FrameworkControl, MappingType
from app.core.wording import say
from app.engine.prioritization_rules import PrioritizationRules
from app.engine.schemas import (
    CapabilityGap,
    CapabilityGating,
    CapabilityPriority,
    CapabilityStatus,
    ImplementationLayer,
    Mandate,
    MandateSource,
    OrdinalLevel,
    PriorityTier,
    RoadmapPhase,
    ZoneContext,
    ZoneDomain,
    ZoneGating,
    ZonePrioritization,
)

# Ordinal scales. They order; they do not add up.
ORDINAL_RANK: dict[OrdinalLevel, int] = {
    OrdinalLevel.LOW: 0,
    OrdinalLevel.MEDIUM: 1,
    OrdinalLevel.HIGH: 2,
}

# How much of the outcome the mechanisms left after gating actually close.
COVERAGE_BANDS: tuple[tuple[float, OrdinalLevel], ...] = (
    (0.9, OrdinalLevel.HIGH),
    (0.6, OrdinalLevel.MEDIUM),
)

# How many other capabilities this one enables (declared dependants).
LEVERAGE_BANDS: tuple[tuple[int, OrdinalLevel], ...] = (
    (2, OrdinalLevel.HIGH),
    (1, OrdinalLevel.MEDIUM),
)

# Gordon-Loeb in spirit, made explicit: risk reduction against cost, resolved by
# a declared table instead of by arithmetic on numbers the engine does not have.
PRIORITY_MATRIX: dict[OrdinalLevel, dict[OrdinalLevel, OrdinalLevel]] = {
    OrdinalLevel.HIGH: {
        OrdinalLevel.LOW: OrdinalLevel.HIGH,
        OrdinalLevel.MEDIUM: OrdinalLevel.HIGH,
        OrdinalLevel.HIGH: OrdinalLevel.MEDIUM,
    },
    OrdinalLevel.MEDIUM: {
        OrdinalLevel.LOW: OrdinalLevel.HIGH,
        OrdinalLevel.MEDIUM: OrdinalLevel.MEDIUM,
        OrdinalLevel.HIGH: OrdinalLevel.LOW,
    },
    OrdinalLevel.LOW: {
        OrdinalLevel.LOW: OrdinalLevel.MEDIUM,
        OrdinalLevel.MEDIUM: OrdinalLevel.LOW,
        OrdinalLevel.HIGH: OrdinalLevel.LOW,
    },
}

# The physical consequence of the asset does not create a number either: it
# raises the benefit one ordinal step, and only where something is actually
# missing in a safety-relevant zone.
HIGH_CONSEQUENCE_SCALES = frozenset({ConsequenceScale.CATASTROPHIC, ConsequenceScale.HIGH})

# The catalog publishes the CIS Implementation Group in `strength`; it is read
# verbatim for CIS controls and never inferred for anything else.
IG_PATTERN = re.compile(r"^IG[1-3]$")
IG_ORDERING_DOMAINS = frozenset({ZoneDomain.IT, ZoneDomain.HYBRID})

MANDATORY_PHASE = 0
PHASE_BY_PRIORITY: dict[OrdinalLevel, int] = {
    OrdinalLevel.HIGH: 1,
    OrdinalLevel.MEDIUM: 2,
    OrdinalLevel.LOW: 3,
}

PHASE_NAMES: dict[int, str] = {
    0: "Fase 0 — Obligatorio por SL-objetivo de la zona y obligación legal",
    1: "Fase 1 — Discrecional de prioridad alta",
    2: "Fase 2 — Discrecional de prioridad media",
    3: "Fase 3 — Discrecional de prioridad baja",
}

PHASE_RATIONALE: dict[int, str] = {
    0: (
        "Bloque obligatorio: no se prioriza y no se ordena entre sí (se lista por identificador, "
        "que no es un ranking). La baseline no puede firmarse mientras quede algún mandato "
        "pendiente en esta fase."
    ),
    1: (
        "Discrecional de prioridad alta: mayor reducción de riesgo por coste según la tabla "
        "ordinal declarada, respetando el orden parcial de dependencias."
    ),
    2: "Discrecional de prioridad media según la tabla ordinal declarada.",
    3: (
        "Discrecional de prioridad baja: se declara y se programa igualmente — dejarla fuera "
        "sería una omisión silenciosa, no una priorización."
    ),
}


@dataclass(frozen=True)
class _Assessment:
    """Everything read about a capability before the roadmap fixes its phase."""

    capability_id: str
    tier: PriorityTier
    layer: ImplementationLayer
    status: CapabilityStatus
    mandates: list[Mandate]
    coverage: float
    coverage_level: OrdinalLevel
    leverage: int
    leverage_level: OrdinalLevel
    depends_on: list[str]
    unlocks: list[str]
    benefit: OrdinalLevel
    uplifted: bool
    cost: OrdinalLevel
    priority: OrdinalLevel | None
    implementation_group: str | None
    band_phase: int
    outstanding: bool
    gap: CapabilityGap | None


def prioritize_zone(
    gating: ZoneGating,
    consequence: ConsequenceScale,
    catalog: Catalog,
    rules: PrioritizationRules,
) -> ZonePrioritization:
    """Tier, order and phase every capability of a zone. None is left out."""
    controls = {c.id: c for c in catalog.controls}
    assessments = {
        capability.capability_id: _assess(
            capability, gating.zone, consequence, catalog, controls, rules
        )
        for capability in gating.capabilities
    }
    phases = _scheduled_phases(assessments, rules)

    capabilities = sorted(
        (
            _item(assessment, phases[assessment.capability_id], gating.zone)
            for assessment in assessments.values()
        ),
        key=lambda item: _order_key(item, gating.zone),
    )
    return ZonePrioritization(
        zone=gating.zone,
        capabilities=capabilities,
        phases=_roadmap(capabilities),
    )


def _assess(
    gating: CapabilityGating,
    zone: ZoneContext,
    consequence: ConsequenceScale,
    catalog: Catalog,
    controls: dict[str, FrameworkControl],
    rules: PrioritizationRules,
) -> _Assessment:
    """Read one capability in one zone: is it mandatory, what does it buy, what does it cost."""
    capability_id = gating.capability_id
    mandates = _mandates(capability_id, zone, catalog, controls, rules)
    tier = PriorityTier.TIER_0 if mandates else PriorityTier.TIER_1

    unlocks = rules.unlocks(capability_id)
    coverage_level = _band(gating.coverage, COVERAGE_BANDS)
    leverage_level = _band(len(unlocks), LEVERAGE_BANDS)
    benefit, uplifted = _benefit(coverage_level, leverage_level, gating, zone, consequence)
    cost = rules.cost_for(capability_id)

    priority = None if tier is PriorityTier.TIER_0 else PRIORITY_MATRIX[benefit][cost]
    band_phase = MANDATORY_PHASE if priority is None else PHASE_BY_PRIORITY[priority]

    return _Assessment(
        capability_id=capability_id,
        tier=tier,
        layer=(
            ImplementationLayer.ORGANIZATIONAL
            if gating.status is CapabilityStatus.DEFERRED_TO_ORGANIZATIONAL_LAYER
            else ImplementationLayer.ASSET
        ),
        status=gating.status,
        mandates=mandates,
        coverage=gating.coverage,
        coverage_level=coverage_level,
        leverage=len(unlocks),
        leverage_level=leverage_level,
        depends_on=rules.requires(capability_id),
        unlocks=unlocks,
        benefit=benefit,
        uplifted=uplifted,
        cost=cost,
        priority=priority,
        implementation_group=_implementation_group(gating, controls),
        band_phase=band_phase,
        outstanding=_is_outstanding(tier, gating),
        gap=gating.gap,
    )


def _mandates(
    capability_id: str,
    zone: ZoneContext,
    catalog: Catalog,
    controls: dict[str, FrameworkControl],
    rules: PrioritizationRules,
) -> list[Mandate]:
    """Why the capability is obligatory here — read from declared data, control by control.

    A mandate is unaffected by gating: that the asset cannot host the mechanism
    does not repeal the requirement. That is precisely what makes a Tier 0
    capability *outstanding* instead of quietly optional.
    """
    found: list[Mandate] = []
    for mapping in sorted(catalog.mappings_for(capability_id), key=lambda m: m.control_id):
        control = controls[mapping.control_id]
        mandate = rules.mandate_for(control.id)

        # A contextual overlay is never a mechanism, so it cannot carry an SL mandate.
        if mandate is not None and mapping.mapping_type is not MappingType.CONTEXTUAL:
            zone_sl = zone.sl_target_for(mandate.foundational_requirement)
            if mandate.mandates_at(zone_sl):
                found.append(
                    Mandate(
                        source=MandateSource.SL_TARGET,
                        control_id=control.id,
                        official_id=control.official_id,
                        framework=control.framework,
                        jurisdiction=control.jurisdiction,
                        foundational_requirement=mandate.foundational_requirement,
                        required_at_sl=mandate.required_at_sl,
                        zone_sl_target=zone_sl,
                        rationale=(
                            f"{mandate.rationale} La zona {zone.zone_id} declara SL-objetivo "
                            f"{zone_sl} en {mandate.foundational_requirement.value} y el "
                            f"requisito es exigible desde SL{mandate.required_at_sl}: la "
                            "capacidad es obligatoria aquí, no discrecional."
                        ),
                    )
                )

        if control.control_type is ControlType.LEGAL:
            found.append(
                Mandate(
                    source=MandateSource.LEGAL_OBLIGATION,
                    control_id=control.id,
                    official_id=control.official_id,
                    framework=control.framework,
                    jurisdiction=control.jurisdiction,
                    rationale=(
                        f"Obligación legal ({control.framework.value} {control.official_id}, "
                        f"jurisdicción {control.jurisdiction.value}): obliga al operador con "
                        "independencia del SL-objetivo. Se acredita en la capa que corresponda, "
                        "pero no se elige."
                    ),
                )
            )
    return found


def _band(value: float, bands: tuple[tuple[float, OrdinalLevel], ...]) -> OrdinalLevel:
    """Place a magnitude on the ordinal scale using the declared thresholds."""
    for threshold, level in bands:
        if value >= threshold:
            return level
    return OrdinalLevel.LOW


def _benefit(
    coverage_level: OrdinalLevel,
    leverage_level: OrdinalLevel,
    gating: CapabilityGating,
    zone: ZoneContext,
    consequence: ConsequenceScale,
) -> tuple[OrdinalLevel, bool]:
    """Ordinal risk reduction: what the capability closes, or what it unlocks.

    The two readings are not averaged — averaging ordinals is the arithmetic
    this engine refuses. The stronger one carries, and the asset's physical
    consequence raises it one step where the zone is safety-relevant and gating
    left something open.
    """
    benefit = max(coverage_level, leverage_level, key=lambda level: ORDINAL_RANK[level])
    uplift = (
        zone.safety_relevant and consequence in HIGH_CONSEQUENCE_SCALES and gating.gap is not None
    )
    if uplift and benefit is not OrdinalLevel.HIGH:
        return _step_up(benefit), True
    return benefit, False


def _step_up(level: OrdinalLevel) -> OrdinalLevel:
    return OrdinalLevel.HIGH if level is OrdinalLevel.MEDIUM else OrdinalLevel.MEDIUM


def _implementation_group(
    gating: CapabilityGating, controls: dict[str, FrameworkControl]
) -> str | None:
    """The CIS IG of what survived gating — an IT prioritisation already done elsewhere."""
    groups = sorted(
        controls[control_id].strength.strip()
        for control_id in (*gating.retained_control_ids, *gating.compensatory_control_ids)
        if control_id in controls
        and controls[control_id].framework is Framework.CIS
        and IG_PATTERN.match(controls[control_id].strength.strip())
    )
    return groups[0] if groups else None


def _is_outstanding(tier: PriorityTier, gating: CapabilityGating) -> bool:
    """A mandate the zone has not met yet: no mechanism left, or a declared residual.

    A capability deferred to the organizational layer is not outstanding *here*:
    it is answered off the asset, and gating already recorded where.
    """
    if tier is not PriorityTier.TIER_0:
        return False
    if gating.status is CapabilityStatus.DEFERRED_TO_ORGANIZATIONAL_LAYER:
        return False
    return gating.status is CapabilityStatus.COMPENSATORY_REQUIRED or gating.gap is not None


def _scheduled_phases(
    assessments: dict[str, _Assessment], rules: PrioritizationRules
) -> dict[str, int]:
    """Apply the partial order: nothing is scheduled before what enables it.

    Tier 0 is exempt on purpose — a mandate is not deferred because a
    discretionary prerequisite is late; the relation is reported instead.
    """
    phases = {capability_id: a.band_phase for capability_id, a in assessments.items()}
    for capability_id in _topological_order(assessments, rules):
        if assessments[capability_id].tier is PriorityTier.TIER_0:
            continue
        prerequisites = [phases[p] for p in rules.requires(capability_id) if p in phases]
        if prerequisites:
            phases[capability_id] = max(phases[capability_id], *prerequisites)
    return phases


def _topological_order(
    assessments: dict[str, _Assessment], rules: PrioritizationRules
) -> list[str]:
    """Prerequisites first. The graph is acyclic — the rule set validates that on load."""
    order: list[str] = []
    seen: set[str] = set()

    def visit(capability_id: str) -> None:
        if capability_id in seen:
            return
        seen.add(capability_id)
        for prerequisite in rules.requires(capability_id):
            if prerequisite in assessments:
                visit(prerequisite)
        order.append(capability_id)

    for capability_id in sorted(assessments):
        visit(capability_id)
    return order


def _item(assessment: _Assessment, phase: int, zone: ZoneContext) -> CapabilityPriority:
    return CapabilityPriority(
        capability_id=assessment.capability_id,
        zone_id=zone.zone_id,
        tier=assessment.tier,
        layer=assessment.layer,
        status=assessment.status,
        mandates=assessment.mandates,
        coverage=assessment.coverage,
        coverage_level=assessment.coverage_level,
        leverage=assessment.leverage,
        unlocks=assessment.unlocks,
        depends_on=assessment.depends_on,
        benefit=assessment.benefit,
        cost=assessment.cost,
        priority=assessment.priority,
        implementation_group=assessment.implementation_group,
        phase=phase,
        outstanding=assessment.outstanding,
        gap=assessment.gap,
        rationale=_rationale(assessment, phase, zone),
    )


def _order_key(item: CapabilityPriority, zone: ZoneContext) -> tuple[int, int, int, int, str]:
    """Roadmap order. Inside phase 0 it is alphabetical — deliberately not a ranking."""
    if item.tier is PriorityTier.TIER_0 or item.priority is None:
        return (item.phase, 0, 0, 0, item.capability_id)
    return (
        item.phase,
        -ORDINAL_RANK[item.priority],
        _implementation_group_rank(item, zone),
        ORDINAL_RANK[item.cost],
        item.capability_id,
    )


def _implementation_group_rank(item: CapabilityPriority, zone: ZoneContext) -> int:
    """IG1 before IG2 before IG3 — but only in IT/hybrid zones, where the IG belongs."""
    if zone.domain not in IG_ORDERING_DOMAINS:
        return 0
    if item.implementation_group is None:
        # No CIS mechanism left: nothing to reuse, so it follows the graded ones.
        return len(PHASE_BY_PRIORITY) + 1
    return int(item.implementation_group.removeprefix("IG"))


def _roadmap(capabilities: list[CapabilityPriority]) -> list[RoadmapPhase]:
    """The phased roadmap. Every phase is emitted, including the empty ones."""
    return [
        RoadmapPhase(
            index=index,
            name=name,
            tier=PriorityTier.TIER_0 if index == MANDATORY_PHASE else PriorityTier.TIER_1,
            capability_ids=[c.capability_id for c in capabilities if c.phase == index],
            rationale=PHASE_RATIONALE[index],
        )
        for index, name in sorted(PHASE_NAMES.items())
    ]


def _rationale(assessment: _Assessment, phase: int, zone: ZoneContext) -> str:
    """Every item says out loud why it sits where it sits."""
    if assessment.tier is PriorityTier.TIER_0:
        sources = ", ".join(sorted({say(m.source) for m in assessment.mandates}))
        note = _mandatory_note(assessment)
        return (
            f"Tier 0 en {zone.zone_id}: obligatoria por {len(assessment.mandates)} mandato(s) "
            f"declarado(s) ({sources}). No se prioriza — se completa: fase {phase}. {note}"
        )

    uplift = (
        " Beneficio elevado un escalón por consecuencia física en zona relevante para safety "
        "con hueco abierto."
        if assessment.uplifted
        else ""
    )
    dependencies = (
        f" Prerrequisitos declarados: {', '.join(assessment.depends_on)}."
        if assessment.depends_on
        else ""
    )
    lift = (
        " La fase se retrasó para no programarla antes que su prerrequisito."
        if phase > assessment.band_phase
        else ""
    )
    group = _group_note(assessment.implementation_group, zone)
    return (
        f"Tier 1 (discrecional) en {zone.zone_id}: beneficio {say(assessment.benefit)} "
        f"(cobertura {assessment.coverage} tras el gating · apalancamiento sobre "
        f"{assessment.leverage} capacidad(es)) frente a coste {say(assessment.cost)} "
        f"-> prioridad {say(assessment.priority) if assessment.priority else 'sin asignar'} por la "
        f"tabla ordinal declarada. Fase {phase}.{uplift}{dependencies}{lift}{group}"
    )


def _mandatory_note(assessment: _Assessment) -> str:
    """What a mandatory capability still owes — said in the terms gating left it in."""
    if assessment.layer is ImplementationLayer.ORGANIZATIONAL:
        return (
            "Se ejerce en la capa organizativa (el gating declaró el ámbito): sigue exigida y se "
            "acredita fuera del activo."
        )
    if not assessment.outstanding:
        return "Cubierta con los mecanismos que el gating deja aplicables en la zona."
    if assessment.status is CapabilityStatus.COMPENSATORY_REQUIRED:
        return (
            "Tras el gating no queda mecanismo aplicable en la zona: el mandato sigue vivo y "
            "exige un control compensatorio compuesto por el humano antes de firmar."
        )
    residual = assessment.gap.residual if assessment.gap else 0.0
    return (
        f"El mejor mecanismo aplicable deja un residuo declarado de {residual}: el mandato no se "
        "da por satisfecho y queda pendiente de cierre antes de firmar."
    )


def _group_note(implementation_group: str | None, zone: ZoneContext) -> str:
    """The IG is always reported; whether it orders depends on the zone."""
    if implementation_group is None:
        return ""
    use = (
        "ordena en esta zona IT/híbrida"
        if zone.domain in IG_ORDERING_DOMAINS
        else f"informativo: en zona {say(zone.domain)} el IG no ordena"
    )
    return f" IG de CIS: {implementation_group} ({use})."
