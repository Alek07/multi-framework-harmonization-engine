"""Two different assets get two measurably different baselines.

The asserted counts are floors, not photographs: they may grow as the rules grow,
and a regression that quietly flattens the engine again will trip them. What must
not change is the shape of the claim: the two profiles differ on many mechanisms;
the crown jewel differs from the corridor it sits behind; no difference is silent;
and the whole thing is deterministic.
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
    """The only thing separating the SIS from the corridor is the profile's `role`.

    Both zones are OT, both safety-relevant, and both declare the same five `nature`
    flags; a rule set that cannot condition on `role` cannot tell them apart at all.
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
