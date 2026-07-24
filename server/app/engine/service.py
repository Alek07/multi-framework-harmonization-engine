"""UCM-8 - Core steps 1-2 end to end, per asset profile.

`resolve_profile` is what the rest of the engine builds on: gating (UCM-9)
removes *mechanisms* from this result, prioritisation (UCM-10) tiers what
survives, and the audit log (UCM-11) records every conflict already resolved
here. No AI takes part: same catalog + same rules + same profile always give
the same result.
"""

from __future__ import annotations

from app.assets.schemas import AssetProfile
from app.catalog.loader import get_catalog
from app.catalog.schemas import Catalog
from app.engine.conflicts import resolve_capability
from app.engine.mapping import map_zone
from app.engine.rules import RuleSet, get_rules
from app.engine.schemas import ProfileResolution, ZoneResolution
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
