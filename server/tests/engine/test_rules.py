"""The rule set loads, is a total order and only names things the catalog has."""

import pytest

from app.catalog.schemas import Catalog, Framework
from app.engine.rules import ResolutionStrategy, RuleSet, load_rules
from app.engine.schemas import ZoneDomain


def test_version(rules: RuleSet) -> None:
    assert rules.rules_version == "0.2.0"


def test_precedence_is_a_total_order_per_domain(rules: RuleSet) -> None:
    for domain in ZoneDomain:
        order = rules.framework_precedence[domain]
        assert set(order) == set(Framework)
        assert len(order) == len(set(order))


def test_precedence_encodes_ics_to_ot_and_nist_to_it(rules: RuleSet) -> None:
    # The two precedences, and the reason they are not the same.
    assert rules.framework_precedence[ZoneDomain.OT][0] is Framework.IEC62443
    assert rules.framework_precedence[ZoneDomain.IT][0] is Framework.CSF
    assert rules.framework_precedence[ZoneDomain.HYBRID][0] is Framework.CSF


def test_legal_overlays_never_lead_the_precedence(rules: RuleSet) -> None:
    # The legal frameworks trail the order: NIS2/IMO/CIRCIA are contextual
    # obligations, and even the TSA — whose SD-02 prescribes a zone mechanism —
    # sits behind the technical norm that dictates *how* the zone implements it.
    # Law demands the outcome; engineering picks the mechanism.
    legal = {Framework.NIS2, Framework.IMO, Framework.CIRCIA, Framework.TSA}
    for domain in ZoneDomain:
        order = rules.framework_precedence[domain]
        assert set(order[-len(legal):]) == legal


def test_rules_validate_against_the_catalog(rules: RuleSet, catalog: Catalog) -> None:
    rules.validate_against(catalog)  # raises if a rule names something non-existent


def test_declared_contradictions_are_seeded(rules: RuleSet) -> None:
    by_id = {c.id: c for c in rules.contradictions}
    assert by_id["CONTRA-MALWARE-AGENT-OT"].resolution is ResolutionStrategy.FRAMEWORK_PRECEDENCE
    assert by_id["CONTRA-AUTH-EMERGENCY-ACCESS"].resolution is ResolutionStrategy.SAFETY_OVERRIDE


def test_safety_override_only_fires_in_safety_relevant_ot_zones(rules: RuleSet) -> None:
    found = rules.contradictions_for("CAP-PR-MFA", ZoneDomain.OT, safety_relevant=True)
    assert [c.id for c in found] == ["CONTRA-AUTH-EMERGENCY-ACCESS"]
    assert rules.contradictions_for("CAP-PR-MFA", ZoneDomain.OT, safety_relevant=False) == []
    assert rules.contradictions_for("CAP-PR-MFA", ZoneDomain.HYBRID, safety_relevant=True) == []


def test_a_rule_cannot_name_a_control_outside_its_capability(catalog: Catalog) -> None:
    rules = load_rules()
    broken = rules.model_copy(deep=True)
    broken.contradictions[0].control_ids = ["CTL-CIS-1001", "CTL-CSF-GVRM01"]
    with pytest.raises(ValueError, match="is not mapped to capability"):
        broken.validate_against(catalog)


def test_precedence_must_cover_every_framework() -> None:
    rules = load_rules()
    data = rules.model_dump(mode="json")
    data["framework_precedence"]["OT"] = ["IEC62443", "CSF"]
    with pytest.raises(ValueError, match="total order"):
        RuleSet.model_validate(data)
