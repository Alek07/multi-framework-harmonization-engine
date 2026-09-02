"""UCM-47 - Sectoral applicability: a norm outside its sector does not apply here.

Mapping and gating answer *which mechanisms exist* and *which this asset can
host*. This module answers a question prior to both: does the norm govern this
asset's sector **at all**? A control that governs ships (IMO MSC.428(98), under
the ISM Code) is not a candidate for an onshore gas pipeline, and offering it
would not be neutrality — it would assert an obligation that does not exist.

It is deliberately *the same operation as gating on another dimension*, and it
reuses the gating machinery rather than inventing one: an asset outside a
control's declared scope becomes a `GatingDecision` with the `NOT_APPLICABLE`
outcome, carrying the rule, the premise observed on the profile (the asset's
sector) and a written justification. Nothing is dropped in silence — the
exclusion is a deliverable of the baseline, visible and auditable.

The match is set intersection: a norm applies to a zone when the sectors it
governs meet the zone's *effective* sectors (its own, or the asset's) in at least
one member. A multisector norm (NIS2 governs eighteen) applies as soon as any one
of them coincides — that "any", not "all", is the rule.

Two asymmetries make the direction of the check safe:

* **Empty scope is transversal.** A control that declares no sector applies to
  every asset (the majority — CIS, CSF and IEC 62443 are cross-sector by
  design), so it is never excluded here. This is the *only* thing that means
  transversal: an enumerated list, however long, is a positive claim and can
  exclude.
* **Unknown asset sectors exclude nothing.** With no sector declared on the zone
  or the asset the engine cannot assert a norm is out of scope, so it offers it:
  a wrong exclusion on a premise nobody stated is the silent restriction the
  whole design forbids. The parse asks for the sectors precisely so this stays a
  reviewed decision, not a guess.

Applicability takes precedence over rule-based gating: "this norm does not govern
your sector" is prior to "your asset cannot host this mechanism" or "this belongs
to the organizational layer". When a gating rule also matched, its id is kept in
`also_matched_rule_ids` so nothing the engine saw is lost.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from app.catalog.schemas import Framework, FrameworkControl, Sector
from app.core.wording import say_all
from app.engine.schemas import GatingDecision, GatingOutcome, ZoneContext

# The declared "rule" of a sectoral exclusion. Unlike a gating rule it lives on
# the control (`applies_to_sectors`), not in the gating JSON, so it needs no id of
# its own per control: this constant names the determination, and the evidence
# names the sectors that made it fire.
SECTOR_APPLICABILITY_RULE_ID = "APPLIC-SECTOR"


def control_applies(control: FrameworkControl, sectors: list[Sector]) -> bool:
    """Whether a control's declared scope meets the zone's effective sectors.

    True when the two sets intersect — one sector in common is enough. Empty
    scope (transversal) and empty effective sectors both return True: see the
    module docstring for why excluding on either would be unsafe.
    """
    scope = control.applies_to_sectors
    if not scope:
        return True
    if not sectors:
        return True
    return bool(set(scope) & set(sectors))


def applicability_decision(
    control: FrameworkControl,
    capability_id: str,
    zone: ZoneContext,
    also_matched_rule_ids: Iterable[str] = (),
) -> GatingDecision | None:
    """A justified `NOT_APPLICABLE` exclusion when the norm is out of the zone's sectors.

    Returns `None` when the control applies (transversal, intersecting, or an
    undeclared sector), so the caller falls through to rule-based gating.
    """
    sectors = zone.sectors
    if control_applies(control, sectors):
        return None

    # Reached only when both sets are non-empty and disjoint: `control_applies`
    # already returned True for an empty scope or empty effective sectors.
    return GatingDecision(
        zone_id=zone.zone_id,
        capability_id=capability_id,
        control_id=control.id,
        outcome=GatingOutcome.NOT_APPLICABLE,
        rule_id=SECTOR_APPLICABILITY_RULE_ID,
        rationale=_rationale(control, sectors),
        evidence=_evidence(control, sectors),
        also_matched_rule_ids=list(also_matched_rule_ids),
    )


def _rationale(control: FrameworkControl, sectors: list[Sector]) -> str:
    governs = say_all(control.applies_to_sectors)
    return (
        f"{control.official_id} no aplica a este activo: rige {governs} y los sectores efectivos "
        f"de la zona son {say_all(sectors)} — la intersección es vacía. "
        f"Exclusión justificada por ámbito sectorial (regla {SECTOR_APPLICABILITY_RULE_ID}): la "
        "norma no gobierna estos sectores, así que ofrecerla afirmaría una obligación que no "
        "existe. Es un entregable de la baseline —lo que se dejó fuera y por qué—, no un hueco; "
        "la capacidad, si otra norma la exige, sigue exigida."
    )


def _evidence(control: FrameworkControl, sectors: list[Sector]) -> list[str]:
    return [
        f"la zona opera en el/los sector(es) {say_all(sectors)}",
        f"la norma rige {say_all(control.applies_to_sectors)} y ninguno coincide",
    ]


def framework_applies(controls: Iterable[FrameworkControl], zone: ZoneContext) -> bool:
    """Whether a legal framework governs this zone at all (UCM-47, framework level).

    True as soon as *one* of the framework's controls applies to the zone's
    sectors — the same "any, not all" rule `control_applies` uses one control at a
    time. A framework with a transversal control (CIRCIA) therefore always
    applies; a purely sectoral one (TSA, NIS2) applies only where its sectors meet
    the zone's. This is the determination the delta reports so the human can choose
    the comparison knowing which regimes are even in play.
    """
    return any(control_applies(control, zone.sectors) for control in controls)


def framework_applicability_reason(
    framework: Framework, controls: Sequence[FrameworkControl], zone: ZoneContext
) -> str:
    """Why a framework does or does not govern this zone, in the operator's words."""
    sectors = zone.sectors
    transversal = any(control.transversal for control in controls)
    governed = sorted(
        {sector for control in controls for sector in control.applies_to_sectors},
        key=lambda sector: sector.value,
    )

    if transversal:
        return (
            f"{framework.value} aplica a este activo: incluye obligaciones transversales que rigen "
            "cualquier sector, así que no depende del sector de la zona. La aplicabilidad la "
            f"determina el motor (regla {SECTOR_APPLICABILITY_RULE_ID}); qué comparar lo elige el "
            "humano."
        )
    if not sectors:
        return (
            f"{framework.value} rige {say_all(governed)} y la zona no declara sector, así que el "
            "motor no puede afirmar que quede fuera de ámbito: se reporta como aplicable para no "
            "restringir en silencio. Declarar el sector de la zona lo convierte en una "
            "determinación firme."
        )
    if framework_applies(controls, zone):
        return (
            f"{framework.value} aplica a este activo: rige {say_all(governed)} y los sectores "
            f"efectivos de la zona son {say_all(sectors)} — la intersección no es vacía. "
            f"Aplicabilidad determinada por ámbito sectorial (regla "
            f"{SECTOR_APPLICABILITY_RULE_ID})."
        )
    return (
        f"{framework.value} no aplica a este activo: rige {say_all(governed)} y los sectores "
        f"efectivos de la zona son {say_all(sectors)} — la intersección es vacía. La comparación "
        "lo sigue mostrando para que la ausencia sea visible, no un silencio."
    )
