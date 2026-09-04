"""A control's declared premise, compared against the zone's own.

The profile always knew the zone hosts no general-purpose OS; since catalog v0.5.0
the control can say it needs one.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.assets.schemas import AssetProfile
from app.catalog.schemas import (
    Catalog,
    ControlStrength,
    Framework,
    FrameworkControl,
    Jurisdiction,
    Presupposition,
)
from app.engine.gating import gate_capability
from app.engine.gating_rules import GatingRules
from app.engine.presuppositions import (
    PREMISE_RULE_ID,
    presupposition_decision,
    unmet_premises,
)
from app.engine.schemas import (
    CandidateOption,
    CapabilityResolution,
    GatingOutcome,
    ZoneContext,
)
from app.engine.zones import zone_context
from tests.engine.conftest import ZONE_ENG, ZONE_OT

CAPABILITY = "CAP-PR-MALWARE"


def control(*premises: dict[str, Any]) -> FrameworkControl:
    """A control that presupposes whatever the test says it does."""
    return FrameworkControl.model_validate(
        {
            "id": "CTL-CIS-1001",
            "framework": Framework.CIS,
            "official_id": "10.1",
            "title": "Deploy and Maintain Anti-Malware Software",
            "paraphrased_description": "Desplegar y mantener software antimalware.",
            "jurisdiction": Jurisdiction.US,
            "strength": ControlStrength(kind="ig", level=1),
            "type": "technical",
            "presupposes": list(premises),
        }
    )


NEEDS_OS = {
    "premise": "general_purpose_os",
    "expected": True,
    "note": "Requiere un sistema operativo donde instalar y mantener el agente.",
}
NEEDS_OFFICE = {
    "premise": "office_it_surface",
    "expected": True,
    "note": "Solo tiene sentido donde se manejan correo y documentos ofimáticos.",
}


@pytest.fixture
def embedded(profile_a: AssetProfile) -> ZoneContext:
    """`Z-OT-CORRIDOR`: an embedded controller. No OS, no users, no office IT."""
    zone = next(z for z in profile_a.zones if z.id == ZONE_OT)
    return zone_context(zone, profile_a)


@pytest.fixture
def workstation(profile_b: AssetProfile) -> ZoneContext:
    """`Z-ENG-STATION`: the five premises all true."""
    zone = next(z for z in profile_b.zones if z.id == ZONE_ENG)
    return zone_context(zone, profile_b)


def test_the_premises_of_the_two_zones_are_actually_opposite(
    embedded: ZoneContext, workstation: ZoneContext
) -> None:
    """The fixtures carry the contrast the whole rule rests on."""
    assert embedded.nature.general_purpose_os is False
    assert workstation.nature.general_purpose_os is True


def test_a_control_declaring_nothing_is_never_excluded(embedded: ZoneContext) -> None:
    """Absence of a premise is not a premise: this is most of the catalog."""
    assert unmet_premises(control(), embedded) == []
    assert presupposition_decision(control(), CAPABILITY, embedded) is None


def test_an_unmet_premise_excludes_the_mechanism_with_its_reason(
    embedded: ZoneContext,
) -> None:
    decision = presupposition_decision(control(NEEDS_OS), CAPABILITY, embedded)

    assert decision is not None
    assert decision.outcome is GatingOutcome.NOT_APPLICABLE
    assert decision.rule_id == PREMISE_RULE_ID
    assert decision.zone_id == ZONE_OT
    # The premise read off the profile, as a sentence the operator can judge.
    assert decision.evidence == [
        "el control presupone que la zona tiene sistema operativo de propósito general, "
        "y la zona declara lo contrario"
    ]
    # The catalog author's own note travels into the justification.
    assert "Requiere un sistema operativo" in decision.rationale
    # Mechanisms leave, capabilities never do.
    assert "nunca la capacidad" in decision.rationale


def test_the_same_control_survives_where_the_premise_holds(workstation: ZoneContext) -> None:
    """Same catalog, two zones, two baselines — which is the thesis."""
    assert presupposition_decision(control(NEEDS_OS), CAPABILITY, workstation) is None


def test_every_unmet_premise_is_named_not_just_the_first(embedded: ZoneContext) -> None:
    decision = presupposition_decision(control(NEEDS_OS, NEEDS_OFFICE), CAPABILITY, embedded)

    assert decision is not None
    assert len(decision.evidence) == 2
    assert "superficie ofimática" in decision.evidence[1]


def test_the_reading_does_not_depend_on_the_order_the_premises_were_written(
    embedded: ZoneContext,
) -> None:
    forwards = presupposition_decision(control(NEEDS_OS, NEEDS_OFFICE), CAPABILITY, embedded)
    backwards = presupposition_decision(control(NEEDS_OFFICE, NEEDS_OS), CAPABILITY, embedded)

    assert forwards is not None and backwards is not None
    assert forwards.outcome is backwards.outcome
    assert sorted(forwards.evidence) == sorted(backwards.evidence)


def test_a_premise_expecting_absence_fires_the_other_way(workstation: ZoneContext) -> None:
    """`expected: false` is the rarer control that exists because a place is *not* something."""
    needs_no_office = {**NEEDS_OFFICE, "expected": False}

    assert presupposition_decision(control(needs_no_office), CAPABILITY, workstation) is not None
    assert presupposition_decision(control(NEEDS_OFFICE), CAPABILITY, workstation) is None


# --- precedence: an authored rule outranks a derived premise ------------------


def _resolution(catalog: Catalog, presupposes: list[dict[str, Any]]) -> CapabilityResolution:
    """`CAP-PR-MALWARE` offering the CIS anti-malware control, with premises attached.

    The control is rebuilt rather than mutated in place: the catalog is read-only
    and a test that edited it would leak into every other one through the
    session-scoped fixture.
    """
    catalog_control = next(c for c in catalog.controls if c.id == "CTL-CIS-1001")
    mapping = next(
        m
        for m in catalog.mappings
        if m.control_id == "CTL-CIS-1001" and m.capability_id == CAPABILITY
    )
    with_premises = catalog_control.model_copy(
        update={"presupposes": [Presupposition.model_validate(p) for p in presupposes]}
    )
    return CapabilityResolution(
        capability=next(c for c in catalog.capabilities if c.id == CAPABILITY),
        zone_id=ZONE_OT,
        options=[CandidateOption(control=with_premises, mapping=mapping)],
        coverage=mapping.coverage_weight,
        has_full_mechanism=True,
    )


def test_an_authored_rule_decides_and_the_derived_premise_stays_on_the_record(
    catalog: Catalog, gating_rules: GatingRules, embedded: ZoneContext
) -> None:
    """Whoever wrote a rule naming this control knew more than its description does.

    `GATE-NA-ANTIMALWARE-AGENT-EMBEDDED` already fires here. The premise agrees
    with it, and must not overwrite it — but neither may the engine forget that
    it also saw the premise.
    """
    gating = gate_capability(_resolution(catalog, [NEEDS_OS]), embedded, gating_rules)
    decision = next(d for d in gating.excluded if d.control_id == "CTL-CIS-1001")

    assert decision.rule_id == "GATE-NA-ANTIMALWARE-AGENT-EMBEDDED"
    assert PREMISE_RULE_ID in decision.also_matched_rule_ids


def test_with_no_authored_rule_the_premise_is_what_excludes(
    catalog: Catalog, gating_rules: GatingRules, embedded: ZoneContext
) -> None:
    """The 118 orphan controls: no rule names them, so nothing used to look."""
    unruled = GatingRules(
        rules_version=gating_rules.rules_version,
        rules=[r for r in gating_rules.rules if "CTL-CIS-1001" not in r.control_ids],
    )

    gating = gate_capability(_resolution(catalog, [NEEDS_OS]), embedded, unruled)
    decision = next(d for d in gating.excluded if d.control_id == "CTL-CIS-1001")

    assert decision.rule_id == PREMISE_RULE_ID
    assert decision.also_matched_rule_ids == []


def test_gating_still_removes_mechanisms_and_never_the_capability(
    catalog: Catalog, gating_rules: GatingRules, embedded: ZoneContext
) -> None:
    gating = gate_capability(_resolution(catalog, [NEEDS_OS]), embedded, gating_rules)

    assert gating.required is True
    assert gating.retained_control_ids == []
    assert gating.capability_id == CAPABILITY
