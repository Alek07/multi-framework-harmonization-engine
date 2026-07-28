"""UCM-12 - The deterministic half: gaps are named, never filled.

These tests never touch a model. What they pin down is the boundary the AI is not
allowed to cross: a draft with a missing target SL does not become a profile with
a plausible one, it becomes a list of questions for the operator.
"""

from __future__ import annotations

import pytest

from app.assets.schemas import AssetProfile
from app.engine.service import resolve_profile
from app.parse.completion import (
    IncompleteDraftError,
    missing_required,
    profile_id_for,
    to_profile,
)
from app.parse.schemas import AssetProfileDraft
from tests.parse.conftest import draft_json


def draft(**overrides: object) -> AssetProfileDraft:
    return AssetProfileDraft.model_validate_json(draft_json(**overrides))


def draft_of(profile: AssetProfile) -> AssetProfileDraft:
    """The same asset expressed as a draft — everything but its identifier."""
    return AssetProfileDraft.model_validate(profile.model_dump(exclude={"id"}))


# --- what is missing -----------------------------------------------------------


def test_empty_draft_reports_every_required_field() -> None:
    gaps = missing_required(AssetProfileDraft())

    assert "name" in gaps
    assert "case" in gaps
    assert "zones" in gaps
    assert "nature.general_purpose_os" in gaps
    assert "criticality.scale" in gaps


def test_unstated_target_sl_is_a_gap_not_a_default() -> None:
    """The failure this whole design exists to prevent: an invented SL."""
    gaps = missing_required(draft())

    assert "zones[Z-ENG-STATION].target_sl" in gaps


def test_gaps_are_named_by_zone_id_so_the_operator_can_find_them() -> None:
    gaps = missing_required(draft(zones=[{"id": "Z-A", "target_sl": 2}, {"id": "Z-B"}]))

    assert "zones[Z-B].target_sl" in gaps
    assert not [gap for gap in gaps if gap.startswith("zones[Z-A]")]


def test_partial_sl_vector_reports_the_missing_frs() -> None:
    """Half a vector is a gap: the parse may keep it, the core may not run on it."""
    gaps = missing_required(
        draft(zones=[{"id": "Z-A", "target_sl": 3, "sl_vector": {"FR1": 3, "FR3": 2}}])
    )

    assert "zones[Z-A].sl_vector.FR2" in gaps
    assert "zones[Z-A].sl_vector.FR7" in gaps
    assert "zones[Z-A].sl_vector.FR1" not in gaps


def test_absent_sl_vector_is_not_a_gap() -> None:
    """`AssetProfile` allows a zone without a vector; only a half one is a gap."""
    gaps = missing_required(draft(zones=[{"id": "Z-A", "target_sl": 3}]))

    assert not [gap for gap in gaps if "sl_vector" in gap]


def test_conduit_without_control_is_a_gap() -> None:
    gaps = missing_required(draft(conduits=[{"id": "C-X", "endpoints": ["Z-A"]}]))

    assert "conduits[C-X].control" in gaps


def test_missing_is_deterministic() -> None:
    assert missing_required(draft()) == missing_required(draft())


# --- promotion to a profile ----------------------------------------------------


def test_promotion_refuses_an_incomplete_draft() -> None:
    with pytest.raises(IncompleteDraftError) as excinfo:
        to_profile(draft())

    assert "zones[Z-ENG-STATION].target_sl" in excinfo.value.missing


def test_promotion_builds_the_profile_once_the_operator_completed_it() -> None:
    reviewed = draft(
        zones=[{"id": "Z-ENG-STATION", "purdue": "L3", "target_sl": 3}],
        nature={
            "general_purpose_os": True,
            "networked": True,
            "hybrid_it_ot": True,
            "interactive_users": True,
            "office_it_surface": True,
        },
        criticality={
            "physical_consequence": "overpressure_rupture_leak",
            "scale": "catastrophic",
            "threat_model": "ATTACK_for_ICS",
        },
    )

    profile = to_profile(reviewed, "PROFILE-C")

    assert profile.id == "PROFILE-C"
    assert profile.zones[0].target_sl == 3
    assert profile.nature.office_it_surface is True


def test_identifier_is_derived_not_asked_of_the_model() -> None:
    assert profile_id_for(draft(name="Estación de ingeniería")) == "ASSET-ESTACION-DE-INGENIERIA"
    assert profile_id_for(draft(name="x"), "PROFILE-C") == "PROFILE-C"
    assert profile_id_for(AssetProfileDraft()) == "ASSET"


# --- fidelity against the hand-written profiles --------------------------------


@pytest.mark.parametrize("fixture", ["profile_a", "profile_b"])
def test_draft_can_express_the_hand_written_profiles(
    fixture: str, request: pytest.FixtureRequest
) -> None:
    """The draft schema is not a lossy summary of `AssetProfile`.

    Both validation profiles (UCM-1/UCM-2) survive a round trip through the
    draft: if the parse cannot represent what an expert wrote by hand, the AI
    layer would be structurally unable to reach the ground truth of M4.
    """
    profile: AssetProfile = request.getfixturevalue(fixture)

    restored = to_profile(draft_of(profile), profile.id)

    assert restored == profile


def test_a_promoted_profile_runs_through_the_core(profile_b: AssetProfile) -> None:
    """The parse's output is an input the deterministic core accepts as-is."""
    restored = to_profile(draft_of(profile_b), profile_b.id)

    assert resolve_profile(restored) == resolve_profile(profile_b)
