"""UCM-10 - The prioritisation rules load, agree with the catalog, and cost everything.

Three inputs the engine is not allowed to invent — what the SL-target mandates,
what enables what, and what it costs — so the rule set has to prove they are
declared, consistent with the catalog, and complete.
"""

import re

import pytest
from pydantic import ValidationError

from app.catalog.schemas import Catalog, Framework
from app.engine.prioritization_rules import (
    CapabilityDependency,
    PrioritizationRules,
    load_prioritization_rules,
)
from app.engine.schemas import FoundationalRequirement, OrdinalLevel

# The catalog publishes the SL of an SR in prose ("base SL1", "requerido a SL2-3");
# the rules declare it as a number. The first SL named must be the same one.
FIRST_SL = re.compile(r"SL(\d)")


def test_version(prioritization_rules: PrioritizationRules) -> None:
    assert prioritization_rules.rules_version == "0.1.0"


def test_rules_validate_against_the_catalog(
    prioritization_rules: PrioritizationRules, catalog: Catalog
) -> None:
    prioritization_rules.validate_against(catalog)


# --- The SL mandate is an IEC scale and must match what the catalog publishes ---


def test_every_iec_control_of_the_catalog_declares_when_it_becomes_mandatory(
    prioritization_rules: PrioritizationRules, catalog: Catalog
) -> None:
    iec = {c.id for c in catalog.controls if c.framework is Framework.IEC62443}
    assert {m.control_id for m in prioritization_rules.sl_mandates} == iec


def test_the_declared_sl_agrees_with_the_strength_the_catalog_publishes(
    prioritization_rules: PrioritizationRules, catalog: Catalog
) -> None:
    controls = {c.id: c for c in catalog.controls}
    for mandate in prioritization_rules.sl_mandates:
        published = FIRST_SL.search(controls[mandate.control_id].strength)
        assert published, controls[mandate.control_id].strength
        assert int(published.group(1)) == mandate.required_at_sl, mandate.control_id


def test_the_declared_fr_agrees_with_the_sr_number(
    prioritization_rules: PrioritizationRules, catalog: Catalog
) -> None:
    """SR 3.4 belongs to FR3: the foundational requirement is not free-form."""
    controls = {c.id: c for c in catalog.controls}
    for mandate in prioritization_rules.sl_mandates:
        official_id = controls[mandate.control_id].official_id  # e.g. "SR 3.4"
        family = official_id.removeprefix("SR ").split(".")[0]
        assert mandate.foundational_requirement.value == f"FR{family}", mandate.control_id


def test_a_mandate_cannot_name_a_control_the_catalog_does_not_have(catalog: Catalog) -> None:
    broken = load_prioritization_rules()
    broken.sl_mandates[0].control_id = "CTL-DOES-NOT-EXIST"
    with pytest.raises(ValueError, match="non-existent control"):
        broken.validate_against(catalog)


def test_the_sl_target_cannot_be_declared_over_a_non_iec_control(catalog: Catalog) -> None:
    # The SL-target is an IEC 62443 scale: declaring one over a CIS safeguard
    # would smuggle a mandate the standard does not make.
    broken = load_prioritization_rules()
    broken.sl_mandates[0].control_id = "CTL-CIS-1001"
    with pytest.raises(ValueError, match="IEC 62443 scale"):
        broken.validate_against(catalog)


def test_a_mandate_fires_only_at_or_above_its_declared_sl(
    prioritization_rules: PrioritizationRules,
) -> None:
    crypto = prioritization_rules.mandate_for("CTL-IEC-SR43")
    assert crypto is not None
    assert crypto.foundational_requirement is FoundationalRequirement.FR4
    assert crypto.required_at_sl == 3
    assert crypto.mandates_at(3) is True
    assert crypto.mandates_at(2) is False


# --- Dependencies are a partial order, and it has to be one -------------------


def test_dependencies_are_acyclic_and_deterministic(
    prioritization_rules: PrioritizationRules,
) -> None:
    assert prioritization_rules.requires("CAP-PR-PATCH") == ["CAP-ID-ASSET", "CAP-ID-RISK"]
    assert prioritization_rules.requires("CAP-ID-ASSET") == []
    # Sorted, so the order never depends on how the file was written.
    for dependency in prioritization_rules.dependencies:
        assert prioritization_rules.requires(dependency.capability_id) == sorted(
            dependency.requires
        )


def test_leverage_is_the_declared_dependants_not_a_guess(
    prioritization_rules: PrioritizationRules,
) -> None:
    unlocked = prioritization_rules.unlocks("CAP-ID-ASSET")
    assert unlocked == sorted(unlocked)
    assert "CAP-PR-PATCH" in unlocked
    assert prioritization_rules.unlocks("CAP-RC-RECOVER") == []


def test_a_capability_cannot_require_itself() -> None:
    with pytest.raises(ValidationError, match="requires itself"):
        CapabilityDependency.model_validate(
            {
                "capability_id": "CAP-ID-ASSET",
                "requires": ["CAP-ID-ASSET"],
                "rationale": "dependencia circular trivial",
            }
        )


def test_a_dependency_cycle_is_rejected() -> None:
    with pytest.raises(ValidationError, match="dependency cycle"):
        PrioritizationRules.model_validate(
            {
                "rules_version": "test",
                "dependencies": [
                    {"capability_id": "A", "requires": ["B"], "rationale": "a<-b"},
                    {"capability_id": "B", "requires": ["C"], "rationale": "b<-c"},
                    {"capability_id": "C", "requires": ["A"], "rationale": "c<-a"},
                ],
            }
        )


def test_a_dependency_cannot_name_a_capability_the_catalog_does_not_have(
    catalog: Catalog,
) -> None:
    broken = load_prioritization_rules()
    broken.dependencies[0].requires = ["CAP-DOES-NOT-EXIST"]
    with pytest.raises(ValueError, match="non-existent capability"):
        broken.validate_against(catalog)


# --- Nothing is prioritised on an undeclared cost -----------------------------


def test_every_capability_of_the_catalog_declares_an_ordinal_cost(
    prioritization_rules: PrioritizationRules, catalog: Catalog
) -> None:
    assert {c.capability_id for c in prioritization_rules.costs} == catalog.capability_ids
    for declared in prioritization_rules.costs:
        assert isinstance(declared.cost, OrdinalLevel)
        assert declared.rationale.strip(), declared.capability_id


def test_a_capability_without_a_declared_cost_is_refused_not_defaulted(catalog: Catalog) -> None:
    """A silent default would be the engine deciding a roadmap on its own."""
    broken = load_prioritization_rules()
    broken.costs = [c for c in broken.costs if c.capability_id != "CAP-PR-MEDIA"]
    with pytest.raises(ValueError, match="without a declared ordinal cost"):
        broken.validate_against(catalog)
    with pytest.raises(KeyError, match="without a declared ordinal cost"):
        broken.cost_for("CAP-PR-MEDIA")


def test_duplicate_entries_are_rejected(prioritization_rules: PrioritizationRules) -> None:
    data = prioritization_rules.model_dump(mode="json")
    data["costs"].append(data["costs"][0])
    with pytest.raises(ValidationError, match="declares the same entry twice"):
        PrioritizationRules.model_validate(data)
