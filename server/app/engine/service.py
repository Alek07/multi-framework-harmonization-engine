"""UCM-8/UCM-9 - Core steps 1-3 end to end, per asset profile.

`resolve_profile` is what the rest of the engine builds on: gating
(`gate_profile`, UCM-9) removes *mechanisms* from this result, prioritisation
(UCM-10) tiers what survives, and the audit log (UCM-11) records every decision
already made here. No AI takes part: same catalog + same rules + same profile
always give the same result.
"""

from __future__ import annotations

from app.assets.schemas import AssetProfile
from app.catalog.loader import get_catalog
from app.catalog.schemas import Catalog
from app.engine.conflicts import resolve_capability
from app.engine.gating import gate_zone
from app.engine.gating_rules import GatingRules, get_gating_rules
from app.engine.mapping import map_zone
from app.engine.rules import RuleSet, get_rules
from app.engine.schemas import ProfileGating, ProfileResolution, ZoneResolution
from app.engine.zones import zone_context


def resolve_profile(
    profile: AssetProfile,
    catalog: Catalog | None = None,
    rules: RuleSet | None = None,
) -> ProfileResolution:
    """Map to neutral capabilities and resolve conflicts, zone by zone."""
    catalog = catalog if catalog is not None else get_catalog()
    rules = rules if rules is not None else get_rules()
    rules.validate_against(catalog)

    zones = [
        ZoneResolution(
            zone=ctx,
            capabilities=[
                resolve_capability(capability, options, rules, ctx)
                for capability, options in map_zone(catalog, rules, ctx)
            ],
        )
        for ctx in (zone_context(z, profile) for z in profile.zones)
    ]

    return ProfileResolution(
        profile_id=profile.id,
        profile_name=profile.name,
        catalog_version=catalog.catalog_version,
        rules_version=rules.rules_version,
        zones=zones,
    )


def gate_profile(
    profile: AssetProfile,
    resolution: ProfileResolution | None = None,
    gating_rules: GatingRules | None = None,
    catalog: Catalog | None = None,
    rules: RuleSet | None = None,
) -> ProfileGating:
    """Apply gating to the resolved profile, zone by zone (UCM-9).

    Takes the resolution rather than recomputing it so the same steps 1-2 result
    can be audited, gated and prioritised: gating decorates, it never re-decides.
    """
    catalog = catalog if catalog is not None else get_catalog()
    resolution = resolution if resolution is not None else resolve_profile(profile, catalog, rules)
    gating_rules = gating_rules if gating_rules is not None else get_gating_rules()
    gating_rules.validate_against(catalog)

    return ProfileGating(
        profile_id=resolution.profile_id,
        profile_name=resolution.profile_name,
        catalog_version=resolution.catalog_version,
        rules_version=resolution.rules_version,
        gating_version=gating_rules.rules_version,
        zones=[gate_zone(zone, profile.nature, gating_rules) for zone in resolution.zones],
    )
