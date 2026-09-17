"""Zone reading: `AssetProfile` -> `ZoneContext`.

The zone's context (IT/OT domain and safety relevance) decides precedence in a
contradiction, so it is derived deterministically and carries a written rationale.
Purdue is an orienting pattern, not an obligation: with no level declared, the
case type decides.
"""

from __future__ import annotations

from app.assets.schemas import AssetProfile, CaseType, ConsequenceScale, Zone
from app.engine.schemas import ZoneContext, ZoneDomain

OT_PURDUE_LEVELS = frozenset({"L0", "L1", "L2"})
IT_PURDUE_LEVELS = frozenset({"L4", "L5"})
PIVOT_PURDUE_LEVEL = "L3"
CROWN_JEWEL_ROLE = "crown_jewel"


def zone_domain(zone: Zone, profile: AssetProfile) -> tuple[ZoneDomain, str]:
    """Read the zone's IT/OT domain, with the rationale of the reading."""
    purdue = (zone.purdue or "").strip().upper()

    if purdue in OT_PURDUE_LEVELS:
        return ZoneDomain.OT, f"nivel Purdue {purdue} (control/supervisión) -> dominio OT"
    if purdue in IT_PURDUE_LEVELS:
        return ZoneDomain.IT, f"nivel Purdue {purdue} (empresa) -> dominio IT"
    if purdue == PIVOT_PURDUE_LEVEL:
        if zone.nature.hybrid_it_ot:
            return (
                ZoneDomain.HYBRID,
                "nivel Purdue L3 con naturaleza híbrida IT/OT -> dominio híbrido",
            )
        return (
            ZoneDomain.OT,
            "nivel Purdue L3 sin naturaleza híbrida -> dominio OT (operaciones de sitio)",
        )

    if profile.case is CaseType.PURE_OT:
        return ZoneDomain.OT, "zona sin nivel Purdue declarado en un activo OT puro -> dominio OT"
    return (
        ZoneDomain.HYBRID,
        "zona sin nivel Purdue declarado en un activo híbrido -> dominio híbrido",
    )


def is_safety_relevant(zone: Zone, profile: AssetProfile, domain: ZoneDomain) -> tuple[bool, str]:
    """Whether the OT safety override applies to the zone, with its rationale.

    Safety engineering itself stays out of scope: this marks only that a mechanism
    must not block the operator in an emergency — a call the engine escalates.
    """
    if zone.safety_out_of_scope:
        return (
            True,
            "zona con función de seguridad declarada fuera de alcance -> relevante para safety",
        )
    if (zone.role or "").strip().lower() == CROWN_JEWEL_ROLE:
        return True, "zona joya de la corona -> relevante para safety"
    if domain is ZoneDomain.OT and profile.criticality.scale is ConsequenceScale.CATASTROPHIC:
        return True, "zona OT con consecuencia física catastrófica -> relevante para safety"
    return (
        False,
        "sin consecuencia física directa desde la zona -> override de seguridad no aplicable",
    )


def zone_context(zone: Zone, profile: AssetProfile) -> ZoneContext:
    """Full zone reading used by mapping and conflict resolution."""
    domain, domain_why = zone_domain(zone, profile)
    safety, safety_why = is_safety_relevant(zone, profile, domain)
    return ZoneContext(
        zone_id=zone.id,
        domain=domain,
        target_sl=zone.target_sl,
        safety_relevant=safety,
        role=(zone.role or "").strip().lower() or None,
        derivation=f"{domain_why}; {safety_why}",
        nature=zone.nature,
        sl_vector=zone.sl_vector,
        sectors=zone.sectors or profile.sectors,
    )
