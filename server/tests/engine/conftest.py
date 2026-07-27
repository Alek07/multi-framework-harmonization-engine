"""UCM-8 - Shared inputs of the deterministic core: catalog, rules and profiles."""

import pytest

from app.assets.loader import get_profile
from app.assets.schemas import AssetProfile
from app.catalog.loader import load_catalog
from app.catalog.schemas import Catalog
from app.engine.rules import RuleSet, load_rules
from app.engine.schemas import ProfileResolution
from app.engine.service import resolve_profile

PROFILE_A = "PROFILE-A"
PROFILE_B = "PROFILE-B"
ZONE_OT = "Z-OT-CORRIDOR"
ZONE_SIS = "Z-SIS"
ZONE_ENG = "Z-ENG-STATION"


@pytest.fixture(scope="session")
def catalog() -> Catalog:
    return load_catalog()


@pytest.fixture(scope="session")
def rules() -> RuleSet:
    return load_rules()


@pytest.fixture(scope="session")
def profile_a() -> AssetProfile:
    return get_profile(PROFILE_A)


@pytest.fixture(scope="session")
def profile_b() -> AssetProfile:
    return get_profile(PROFILE_B)


@pytest.fixture(scope="session")
def resolution_a(profile_a: AssetProfile, catalog: Catalog, rules: RuleSet) -> ProfileResolution:
    return resolve_profile(profile_a, catalog, rules)


@pytest.fixture(scope="session")
def resolution_b(profile_b: AssetProfile, catalog: Catalog, rules: RuleSet) -> ProfileResolution:
    return resolve_profile(profile_b, catalog, rules)
