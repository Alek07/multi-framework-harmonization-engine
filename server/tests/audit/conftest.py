"""Fixtures of the traceable log: the service and the two runs' trails."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.schemas import AssetProfile
from app.audit.repository import AuditRepository
from app.audit.schemas import AuditEventCreate
from app.audit.service import AuditService
from app.audit.trail import trail_for_core_run
from app.engine.schemas import ProfileGating, ProfilePrioritization, ProfileResolution

# Fixed run ids: the trail is deterministic, so the tests are too.
RUN_A = UUID("11111111-1111-1111-1111-111111111111")
RUN_B = UUID("22222222-2222-2222-2222-222222222222")


@pytest.fixture
def audit(db: AsyncSession) -> AuditService:
    return AuditService(AuditRepository(db))


@pytest.fixture
def run_id() -> UUID:
    return uuid4()


@pytest.fixture(scope="session")
def trail_a(
    profile_a: AssetProfile,
    resolution_a: ProfileResolution,
    gating_a: ProfileGating,
    priorities_a: ProfilePrioritization,
) -> list[AuditEventCreate]:
    return trail_for_core_run(profile_a, resolution_a, gating_a, priorities_a, RUN_A)


@pytest.fixture(scope="session")
def trail_b(
    profile_b: AssetProfile,
    resolution_b: ProfileResolution,
    gating_b: ProfileGating,
    priorities_b: ProfilePrioritization,
) -> list[AuditEventCreate]:
    return trail_for_core_run(profile_b, resolution_b, gating_b, priorities_b, RUN_B)
