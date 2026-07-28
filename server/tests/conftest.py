"""Shared fixtures: the in-memory database and the versioned inputs of the core.

The catalog, the rules and the two hand-written profiles are inputs of the whole
POC, not only of the engine: the audit-log tests (UCM-11) record the very same
runs the engine tests assert on, so the core fixtures live here.
"""

from collections.abc import AsyncGenerator, Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.assets.loader import get_profile
from app.assets.schemas import AssetProfile
from app.catalog.loader import load_catalog
from app.catalog.schemas import Catalog
from app.core.config import settings
from app.core.database import get_db
from app.engine.gating_rules import GatingRules, load_gating_rules
from app.engine.prioritization_rules import PrioritizationRules, load_prioritization_rules
from app.engine.rules import RuleSet, load_rules
from app.engine.schemas import ProfileGating, ProfilePrioritization, ProfileResolution
from app.engine.service import gate_profile, prioritize_profile, resolve_profile
from app.main import app
from app.models.registry import Base

PROFILE_A = "PROFILE-A"
PROFILE_B = "PROFILE-B"

# The tests own their schema: it is created and dropped per test on an in-memory
# database, so the app's startup must not touch the configured SQLite file.
settings.CREATE_TABLES_ON_STARTUP = False

engine = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with TestSessionLocal() as session:
        yield session


app.dependency_overrides[get_db] = _override_get_db


@pytest.fixture(autouse=True)
async def _setup_db() -> AsyncGenerator[None, None]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    async with TestSessionLocal() as session:
        yield session


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as c:
        yield c


# --- versioned inputs and core runs (UCM-8/UCM-9/UCM-10) ----------------------


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


@pytest.fixture(scope="session")
def gating_rules() -> GatingRules:
    return load_gating_rules()


@pytest.fixture(scope="session")
def gating_a(
    profile_a: AssetProfile,
    resolution_a: ProfileResolution,
    gating_rules: GatingRules,
    catalog: Catalog,
) -> ProfileGating:
    return gate_profile(profile_a, resolution_a, gating_rules, catalog)


@pytest.fixture(scope="session")
def gating_b(
    profile_b: AssetProfile,
    resolution_b: ProfileResolution,
    gating_rules: GatingRules,
    catalog: Catalog,
) -> ProfileGating:
    return gate_profile(profile_b, resolution_b, gating_rules, catalog)


@pytest.fixture(scope="session")
def prioritization_rules() -> PrioritizationRules:
    return load_prioritization_rules()


@pytest.fixture(scope="session")
def priorities_a(
    profile_a: AssetProfile,
    gating_a: ProfileGating,
    prioritization_rules: PrioritizationRules,
    catalog: Catalog,
) -> ProfilePrioritization:
    return prioritize_profile(profile_a, gating_a, prioritization_rules, catalog)


@pytest.fixture(scope="session")
def priorities_b(
    profile_b: AssetProfile,
    gating_b: ProfileGating,
    prioritization_rules: PrioritizationRules,
    catalog: Catalog,
) -> ProfilePrioritization:
    return prioritize_profile(profile_b, gating_b, prioritization_rules, catalog)
