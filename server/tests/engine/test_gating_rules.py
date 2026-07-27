"""UCM-9 - The gating rules load, only speak of declared premises, and never gate in silence."""

import pytest
from pydantic import ValidationError

from app.assets.schemas import TechNature
from app.catalog.schemas import Catalog
from app.engine.gating_rules import GatingRule, GatingRules, load_gating_rules
from app.engine.schemas import GatingOutcome, ZoneContext, ZoneDomain

ZONE = ZoneContext(
    zone_id="Z-TEST",
    domain=ZoneDomain.OT,
    target_sl=3,
    safety_relevant=True,
    derivation="zona de prueba",
)
EMBEDDED = TechNature(
    general_purpose_os=False,
    networked=True,
    hybrid_it_ot=False,
    interactive_users=False,
    office_it_surface=False,
)


def test_version(gating_rules: GatingRules) -> None:
    assert gating_rules.rules_version == "0.1.0"


def test_the_three_outcomes_of_the_ticket_are_all_seeded(gating_rules: GatingRules) -> None:
    assert {r.outcome for r in gating_rules.rules} == set(GatingOutcome)


def test_rules_validate_against_the_catalog(gating_rules: GatingRules, catalog: Catalog) -> None:
    gating_rules.validate_against(catalog)  # raises if a rule gates a non-existent control


def test_a_rule_cannot_gate_a_control_the_catalog_does_not_have(catalog: Catalog) -> None:
    broken = load_gating_rules()
    broken.rules[0].control_ids = ["CTL-DOES-NOT-EXIST"]
    with pytest.raises(ValueError, match="non-existent control"):
        broken.validate_against(catalog)


def test_a_condition_cannot_invoke_a_premise_the_profile_does_not_declare() -> None:
    # The gating only reads what the AssetProfile states; it may not invent premises.
    with pytest.raises(ValidationError, match="non-existent profile premises"):
        GatingRule.model_validate(
            {
                "id": "GATE-TEST",
                "outcome": "not_applicable",
                "control_ids": ["CTL-CIS-1001"],
                "applies_when": {"nature": {"has_a_screen": False}},
                "rationale": "premisa inventada",
            }
        )


def test_every_condition_flag_matches_a_field_of_the_profile(
    gating_rules: GatingRules,
) -> None:
    for rule in gating_rules.rules:
        assert set(rule.applies_when.nature) <= set(TechNature.model_fields), rule.id


# --- "Never silently" is enforced by the schema, not by good intentions -------


def test_a_wrong_scope_rule_must_name_the_layer_it_defers_to() -> None:
    with pytest.raises(ValidationError, match="must name the layer it defers to"):
        GatingRule.model_validate(
            {
                "id": "GATE-TEST",
                "outcome": "wrong_scope",
                "control_ids": ["CTL-CSF-GVRM01"],
                "rationale": "no es mecanismo de zona",
            }
        )


def test_an_objective_without_mechanism_must_declare_its_compensation() -> None:
    with pytest.raises(ValidationError, match="must declare the compensation"):
        GatingRule.model_validate(
            {
                "id": "GATE-TEST",
                "outcome": "objective_without_mechanism",
                "control_ids": ["CTL-CIS-0605"],
                "rationale": "el activo no puede hospedar el mecanismo",
            }
        )


def test_only_an_orphaned_objective_owes_a_compensation() -> None:
    with pytest.raises(ValidationError, match="owes a compensation"):
        GatingRule.model_validate(
            {
                "id": "GATE-TEST",
                "outcome": "not_applicable",
                "control_ids": ["CTL-CIS-1001"],
                "rationale": "sin premisa técnica",
                "compensation": "una compensación que esta salida no debe prometer",
            }
        )


def test_duplicate_rule_ids_are_rejected(gating_rules: GatingRules) -> None:
    data = gating_rules.model_dump(mode="json")
    data["rules"].append(data["rules"][0])
    with pytest.raises(ValidationError, match="Duplicate gating rule IDs"):
        GatingRules.model_validate(data)


# --- Determinism -------------------------------------------------------------


def test_matching_rules_come_back_in_declared_order_not_file_order() -> None:
    """Two rules on the same control: the outcome precedence decides, not the file."""
    data = {
        "rules_version": "test",
        "rules": [
            {
                "id": "GATE-Z-OWM",
                "outcome": "objective_without_mechanism",
                "control_ids": ["CTL-CIS-1001"],
                "rationale": "objetivo sin mecanismo",
                "compensation": "control compensatorio declarado",
            },
            {
                "id": "GATE-A-SCOPE",
                "outcome": "wrong_scope",
                "control_ids": ["CTL-CIS-1001"],
                "rationale": "ámbito equivocado",
                "deferred_to": "capa organizativa",
            },
        ],
    }
    rules = GatingRules.model_validate(data)
    reversed_rules = GatingRules.model_validate({**data, "rules": list(reversed(data["rules"]))})

    for candidate in (rules, reversed_rules):
        matched = candidate.rules_for("CTL-CIS-1001", ZONE, EMBEDDED)
        assert [r.id for r in matched] == ["GATE-A-SCOPE", "GATE-Z-OWM"]


def test_a_rule_whose_premises_do_not_hold_does_not_fire(gating_rules: GatingRules) -> None:
    hybrid_host = EMBEDDED.model_copy(update={"general_purpose_os": True})
    assert gating_rules.rules_for("CTL-CIS-1001", ZONE, EMBEDDED)
    assert gating_rules.rules_for("CTL-CIS-1001", ZONE, hybrid_host) == []


def test_an_unconditional_rule_still_states_its_ground(gating_rules: GatingRules) -> None:
    governance = next(r for r in gating_rules.rules if r.id == "GATE-SCOPE-GOVERNANCE")
    assert governance.applies_when.evidence(ZONE, EMBEDDED) == ["applies_when=unconditional"]
