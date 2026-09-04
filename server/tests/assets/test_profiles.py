"""The two hand-written profiles load and match their M0 definition."""

from app.assets.loader import available_profiles, get_profile
from app.assets.schemas import CaseType, ConsequenceScale

PROFILE_A = get_profile("PROFILE-A")
PROFILE_B = get_profile("PROFILE-B")


def test_both_profiles_are_frozen_in_the_repo() -> None:
    assert available_profiles() == ["PROFILE-A", "PROFILE-B"]


def test_profile_a_is_pure_ot_with_a_segregated_sis() -> None:
    assert PROFILE_A.case is CaseType.PURE_OT
    assert [z.id for z in PROFILE_A.zones] == ["Z-OT-CORRIDOR", "Z-SIS"]
    sis = PROFILE_A.zones[1]
    assert sis.role == "crown_jewel"
    assert sis.safety_out_of_scope is True
    assert all(z.nature.general_purpose_os is False for z in PROFILE_A.zones)
    assert PROFILE_A.criticality.scale is ConsequenceScale.CATASTROPHIC


def test_profile_b_is_hybrid_north_of_the_idmz() -> None:
    assert PROFILE_B.case is CaseType.HYBRID_IT_OT
    station = PROFILE_B.zones[0]
    assert station.purdue == "L3"
    assert station.position == "north_of_idmz"
    assert station.nature.hybrid_it_ot is True
    assert station.nature.office_it_surface is True


def test_the_sl_vectors_contrast_as_designed() -> None:
    # A = {3,3,3,2,3,3,3} (FR4 down, pure OT) · B = {3,3,3,3,3,3,2} (FR4 up, FR7 down).
    corridor = PROFILE_A.zones[0].sl_vector
    station = PROFILE_B.zones[0].sl_vector
    assert corridor is not None and station is not None
    assert (corridor.FR4, corridor.FR7) == (2, 3)
    assert (station.FR4, station.FR7) == (3, 2)
    assert PROFILE_A.zones[0].target_sl == PROFILE_B.zones[0].target_sl == 3
