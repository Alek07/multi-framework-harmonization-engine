"""The zone reading that decides precedence is derived, not assumed."""

from app.assets.schemas import AssetProfile
from app.engine.schemas import ZoneDomain
from app.engine.zones import zone_context
from tests.engine.conftest import ZONE_ENG, ZONE_OT, ZONE_SIS


def _context(profile: AssetProfile, zone_id: str):
    zone = next(z for z in profile.zones if z.id == zone_id)
    return zone_context(zone, profile)


def test_control_zone_reads_as_ot_and_safety_relevant(profile_a: AssetProfile) -> None:
    ctx = _context(profile_a, ZONE_OT)
    assert ctx.domain is ZoneDomain.OT
    assert ctx.safety_relevant is True
    assert ctx.target_sl == 3


def test_sis_zone_without_purdue_falls_back_to_the_case_type(profile_a: AssetProfile) -> None:
    # Z-SIS declares no Purdue level: the pure-OT case decides, and the declared
    # safety scope makes it safety-relevant.
    ctx = _context(profile_a, ZONE_SIS)
    assert ctx.domain is ZoneDomain.OT
    assert ctx.safety_relevant is True


def test_engineering_station_reads_as_hybrid_and_not_safety_relevant(
    profile_b: AssetProfile,
) -> None:
    # L3 north of the IDMZ: it pivots into OT but is not a real-time control element.
    ctx = _context(profile_b, ZONE_ENG)
    assert ctx.domain is ZoneDomain.HYBRID
    assert ctx.safety_relevant is False


def test_every_reading_carries_its_rationale(
    profile_a: AssetProfile, profile_b: AssetProfile
) -> None:
    for profile in (profile_a, profile_b):
        for zone in profile.zones:
            assert zone_context(zone, profile).derivation.strip()
