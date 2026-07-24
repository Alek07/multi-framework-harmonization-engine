"""UCM-8 - Resolution must not depend on the order the catalog was ingested.

The ticket demands this be proven, not asserted: the catalog is shuffled with
several fixed seeds and the whole resolution must come out byte-identical.
"""

import random

from app.assets.schemas import AssetProfile
from app.catalog.schemas import Catalog
from app.engine.rules import RuleSet
from app.engine.service import resolve_profile

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
