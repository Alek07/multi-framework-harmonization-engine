"""UCM-8/UCM-9 - The core must not depend on the order its inputs were ingested.

The ticket demands this be proven, not asserted: the catalog is shuffled with
several fixed seeds and the whole resolution — and the gating built on it — must
come out byte-identical.
"""

import random

from app.assets.schemas import AssetProfile
from app.catalog.schemas import Catalog
from app.engine.gating_rules import GatingRules
from app.engine.rules import RuleSet
from app.engine.service import gate_profile, resolve_profile

SEEDS = (1, 7, 42, 1337)


def _shuffled(catalog: Catalog, seed: int) -> Catalog:
    rng = random.Random(seed)
    shuffled = catalog.model_copy(deep=True)
    for items in (shuffled.capabilities, shuffled.controls, shuffled.mappings):
        rng.shuffle(items)
    return shuffled


def test_shuffling_the_catalog_changes_nothing(
    profile_a: AssetProfile, profile_b: AssetProfile, catalog: Catalog, rules: RuleSet
) -> None:
    for profile in (profile_a, profile_b):
        baseline = resolve_profile(profile, catalog, rules).model_dump(mode="json")
        for seed in SEEDS:
            other = resolve_profile(profile, _shuffled(catalog, seed), rules).model_dump(
                mode="json"
            )
            assert other == baseline, f"resolution depends on ingestion order (seed {seed})"


def test_shuffling_the_declared_rules_changes_nothing(
    profile_a: AssetProfile, catalog: Catalog, rules: RuleSet
) -> None:
    baseline = resolve_profile(profile_a, catalog, rules).model_dump(mode="json")
    reversed_rules = rules.model_copy(deep=True)
    reversed_rules.contradictions.reverse()
    for contradiction in reversed_rules.contradictions:
        contradiction.control_ids.reverse()
    other = resolve_profile(profile_a, catalog, reversed_rules).model_dump(mode="json")
    assert other == baseline


def test_resolution_is_repeatable(
    profile_a: AssetProfile, catalog: Catalog, rules: RuleSet
) -> None:
    first = resolve_profile(profile_a, catalog, rules).model_dump(mode="json")
    second = resolve_profile(profile_a, catalog, rules).model_dump(mode="json")
    assert first == second


def _gate(
    profile: AssetProfile, catalog: Catalog, rules: RuleSet, gating_rules: GatingRules
) -> dict:
    resolution = resolve_profile(profile, catalog, rules)
    return gate_profile(profile, resolution, gating_rules, catalog).model_dump(mode="json")


def test_shuffling_the_catalog_changes_no_gating_decision(
    profile_a: AssetProfile,
    profile_b: AssetProfile,
    catalog: Catalog,
    rules: RuleSet,
    gating_rules: GatingRules,
) -> None:
    for profile in (profile_a, profile_b):
        baseline = _gate(profile, catalog, rules, gating_rules)
        for seed in SEEDS:
            other = _gate(profile, _shuffled(catalog, seed), rules, gating_rules)
            assert other == baseline, f"gating depends on ingestion order (seed {seed})"


def test_shuffling_the_gating_rules_changes_nothing(
    profile_a: AssetProfile, catalog: Catalog, rules: RuleSet, gating_rules: GatingRules
) -> None:
    baseline = _gate(profile_a, catalog, rules, gating_rules)
    reversed_rules = gating_rules.model_copy(deep=True)
    reversed_rules.rules.reverse()
    for rule in reversed_rules.rules:
        rule.control_ids.reverse()
    assert _gate(profile_a, catalog, rules, reversed_rules) == baseline
