"""UCM-8 - The core runs end to end with the two hand-written profiles (M1 gate, no AI)."""

from app.assets.schemas import AssetProfile
from app.catalog.schemas import Catalog
from app.engine.schemas import CandidateStatus, ProfileResolution
from app.engine.service import prioritize_profile
from tests.engine.conftest import ZONE_ENG, ZONE_OT, ZONE_SIS


def test_both_profiles_resolve_against_the_versioned_inputs(
    resolution_a: ProfileResolution, resolution_b: ProfileResolution
) -> None:
    assert resolution_a.profile_id == "PROFILE-A"
    assert resolution_b.profile_id == "PROFILE-B"
    for resolution in (resolution_a, resolution_b):
        assert resolution.catalog_version == "0.3.0"
        assert resolution.rules_version == "0.1.0"


def test_the_zones_of_each_profile_are_resolved(
    resolution_a: ProfileResolution, resolution_b: ProfileResolution
) -> None:
    assert [z.zone.zone_id for z in resolution_a.zones] == [ZONE_OT, ZONE_SIS]
    assert [z.zone.zone_id for z in resolution_b.zones] == [ZONE_ENG]


def test_zero_silent_omissions(
    resolution_a: ProfileResolution, resolution_b: ProfileResolution, catalog: Catalog
) -> None:
    """The measured invariant: whatever is not covered is named, never dropped."""
    for resolution in (resolution_a, resolution_b):
        for zone in resolution.zones:
            for capability in zone.capabilities:
                if capability.gap is None:
                    assert capability.has_full_mechanism and capability.coverage == 1.0
                else:
                    assert capability.gap.rationale.strip()
            # Every capability of the catalog is accounted for in every zone.
            assert len(zone.capabilities) == len(catalog.capabilities)


def test_every_engine_decision_carries_a_reason(
    resolution_a: ProfileResolution, resolution_b: ProfileResolution
) -> None:
    for resolution in (resolution_a, resolution_b):
        for conflict in resolution.conflicts:
            assert conflict.rationale.strip()
        for zone in resolution.zones:
            for capability in zone.capabilities:
                for option in capability.options:
                    if option.status is not CandidateStatus.ELIGIBLE:
                        assert option.status_reason, option.control_id


def test_same_catalog_different_zone_gives_a_different_resolution(
    resolution_a: ProfileResolution, resolution_b: ProfileResolution
) -> None:
    """The contrast the pair of profiles exists to show."""
    superseded_ot = {
        o.control_id
        for c in resolution_a.zone(ZONE_OT).capabilities
        for o in c.options
        if o.status is CandidateStatus.SUPERSEDED
    }
    superseded_hybrid = {
        o.control_id
        for c in resolution_b.zone(ZONE_ENG).capabilities
        for o in c.options
        if o.status is CandidateStatus.SUPERSEDED
    }
    assert superseded_ot and superseded_hybrid
    assert superseded_ot != superseded_hybrid
    assert len(resolution_a.open_decisions) > len(resolution_b.open_decisions)


def test_the_four_steps_run_from_the_profile_alone(
    profile_a: AssetProfile, profile_b: AssetProfile
) -> None:
    """M1 gate: mapping, conflicts, gating and roadmap with the versioned inputs only."""
    for profile in (profile_a, profile_b):
        priorities = prioritize_profile(profile)
        assert [z.zone.zone_id for z in priorities.zones] == [z.id for z in profile.zones]
        assert all(zone.phases and zone.capabilities for zone in priorities.zones)
