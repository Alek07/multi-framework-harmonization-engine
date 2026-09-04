"""Sectoral applicability: a norm outside its sector does not apply here.

Prior to mapping and gating: does the norm govern this asset's sector at all? An
out-of-scope control becomes a `GatingDecision` with the `NOT_APPLICABLE` outcome
(same machinery as gating), never a silent drop. The match is set intersection on
the zone's effective sectors — any member in common, not all.

Two asymmetries keep the check safe: empty scope is transversal (applies to every
asset, never excluded), and unknown asset sectors exclude nothing (the engine
cannot assert out-of-scope on a premise nobody stated). Applicability takes
precedence over rule-based gating; a matched gating rule is kept in
`also_matched_rule_ids`.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from app.catalog.schemas import Framework, FrameworkControl, Sector
from app.core.wording import say_all
from app.engine.schemas import GatingDecision, GatingOutcome, ZoneContext

# Rule id of a sectoral exclusion: it lives on the control (`applies_to_sectors`),
# not in the gating JSON, so one constant names the determination.
SECTOR_APPLICABILITY_RULE_ID = "APPLIC-SECTOR"


def control_applies(control: FrameworkControl, sectors: list[Sector]) -> bool:
    """Whether a control's declared scope meets the zone's effective sectors.

    True on intersection, and also on empty scope (transversal) or empty
    effective sectors — excluding on either would be unsafe (see module docstring).
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

    Returns `None` when the control applies, so the caller falls through to
    rule-based gating.
    """
    sectors = zone.sectors
    if control_applies(control, sectors):
        return None

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
    """Whether a legal framework governs this zone at all (framework level).

    True as soon as one of its controls applies (any, not all): a framework with
    a transversal control always applies, a purely sectoral one only where its
    sectors meet the zone's. The delta reports it so the human knows which regimes
    are in play.
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
