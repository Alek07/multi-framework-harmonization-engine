"""Core steps 1-4 end to end, per asset profile.

`resolve_profile` maps and resolves; `gate_profile` removes mechanisms;
`prioritize_profile` tiers what survives into a phased roadmap. No AI takes part:
same catalog + rules + profile always give the same result.
"""

from __future__ import annotations

from app.assets.schemas import AssetProfile
from app.catalog.loader import get_catalog
from app.catalog.schemas import Catalog
from app.engine.conflicts import resolve_capability
from app.engine.gating import gate_zone
from app.engine.gating_rules import GatingRules, get_gating_rules
from app.engine.mapping import map_zone
from app.engine.prioritization import prioritize_zone
from app.engine.prioritization_rules import PrioritizationRules, get_prioritization_rules
from app.engine.rules import RuleSet, get_rules
from app.engine.schemas import (
    ProfileGating,
    ProfilePrioritization,
    ProfileResolution,
    ZoneResolution,
)
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
    """Apply gating to the resolved profile, zone by zone.

    Takes the resolution rather than recomputing it, so one steps 1-2 result is
    audited, gated and prioritised: gating decorates, it never re-decides.
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
        zones=[gate_zone(zone, gating_rules) for zone in resolution.zones],
    )


def prioritize_profile(
    profile: AssetProfile,
    gating: ProfileGating | None = None,
    prioritization_rules: PrioritizationRules | None = None,
    catalog: Catalog | None = None,
    rules: RuleSet | None = None,
    gating_rules: GatingRules | None = None,
) -> ProfilePrioritization:
    """Tier, order and phase the gated profile, zone by zone.

    Takes the gating rather than recomputing it: one chain of decisions, auditable
    end to end. It reads what gating left applicable — never re-opening a mechanism
    nor repealing a mandate gating could not meet.
    """
    catalog = catalog if catalog is not None else get_catalog()
    if gating is None:
        gating = gate_profile(profile, None, gating_rules, catalog, rules)
    prioritization_rules = (
        prioritization_rules if prioritization_rules is not None else get_prioritization_rules()
    )
    prioritization_rules.validate_against(catalog)

    return ProfilePrioritization(
        profile_id=gating.profile_id,
        profile_name=gating.profile_name,
        catalog_version=gating.catalog_version,
        rules_version=gating.rules_version,
        gating_version=gating.gating_version,
        prioritization_version=prioritization_rules.rules_version,
        zones=[
            prioritize_zone(zone, profile.criticality.scale, catalog, prioritization_rules)
            for zone in gating.zones
        ],
    )
