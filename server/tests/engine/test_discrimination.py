"""UCM-44 - Two different assets get two measurably different baselines.

This is the claim the whole engine rests on, and until v0.2.0 of the gating rules
it was not true enough to demonstrate: against the v0.2.0 catalog the previous
rule set named 20 of 225 controls and left exactly 7 of them behaving differently
between a Purdue-L1 gas corridor and a hybrid Windows engineering station. Every
other mechanism was retained identically, so the operator's asset barely moved
their baseline.

The numbers asserted here are floors, not photographs: they may grow as the rules
grow, and a regression that quietly flattens the engine again will trip them. What
must not change is the shape of the claim:

* the two profiles differ on a substantial number of mechanisms;
* the crown jewel differs from the corridor it sits behind, which needs a premise
  the profile declares (`role`) and v0.1.0 could not read at all;
* no difference is silent — each one traces to a rule, a premise observed on the
  profile and a written justification;
* and the whole thing is deterministic: the same inputs give the same answer.
"""

from __future__ import annotations

from app.catalog.schemas import Catalog
from app.engine.schemas import ProfileGating

RETAINED = "retenido"


def outcomes(gating: ProfileGating, zone_id: str, catalog: Catalog) -> dict[str, str]:
    """How each catalog control ends up in one zone: retained, or its exclusion."""
    zone = gating.zone(zone_id)
    retained = {
        control_id
        for capability in zone.capabilities
        for control_id in (*capability.retained_control_ids, *capability.compensatory_control_ids)
    }
    excluded: dict[str, str] = {}
    for decision in zone.decisions:
        excluded.setdefault(decision.control_id, decision.outcome.value)
    return {
        control.id: RETAINED if control.id in retained else excluded.get(control.id, RETAINED)
        for control in catalog.controls
    }


def differing(a: dict[str, str], b: dict[str, str]) -> set[str]:
    return {control_id for control_id in a if a[control_id] != b[control_id]}


def test_two_profiles_produce_measurably_different_baselines(
    gating_a: ProfileGating, gating_b: ProfileGating, catalog: Catalog
) -> None:
    corridor = outcomes(gating_a, "Z-OT-CORRIDOR", catalog)
    station = outcomes(gating_b, "Z-ENG-STATION", catalog)

    # 23 at the time of writing, against 7 with the v0.1.0 rule set.
    assert len(differing(corridor, station)) >= 20


def test_the_crown_jewel_is_not_the_corridor_it_sits_behind(
    gating_a: ProfileGating, catalog: Catalog
) -> None:
    """0 with the v0.1.0 rules: no premise the engine could read told them apart.

    Both zones are OT, both are safety-relevant — the corridor because its physical
    consequence is catastrophic — and both declare the same five `nature` flags. The
    only thing that separates the safety instrumented system from the corridor is
    the role the profile declares for it, and until UCM-44 no rule could condition
    on it.
    """
    corridor = outcomes(gating_a, "Z-OT-CORRIDOR", catalog)
    sis = outcomes(gating_a, "Z-SIS", catalog)
    apart = differing(corridor, sis)

    assert len(apart) >= 5
    # And it is the SIS that admits *less*, never more.
    assert all(sis[control_id] != RETAINED for control_id in apart)


def test_no_difference_between_zones_is_silent(
    gating_a: ProfileGating, gating_b: ProfileGating
) -> None:
    """Every exclusion carries its rule, the premise it read and a written reason."""
    for gating in (gating_a, gating_b):
        for zone in gating.zones:
            for decision in zone.decisions:
                assert decision.rule_id
                assert decision.evidence
                assert decision.rationale.strip()
                if decision.outcome.value == "objective_without_mechanism":
                    assert decision.compensation
                if decision.outcome.value == "wrong_scope":
                    assert decision.deferred_to


def test_the_difference_is_reproducible(gating_a: ProfileGating, catalog: Catalog) -> None:
    """A measurement nobody can repeat is not a measurement."""
    from app.assets.loader import get_profile
    from app.engine.service import gate_profile

    again = gate_profile(get_profile("PROFILE-A"))

    for zone_id in ("Z-OT-CORRIDOR", "Z-SIS"):
        assert outcomes(again, zone_id, catalog) == outcomes(gating_a, zone_id, catalog)
