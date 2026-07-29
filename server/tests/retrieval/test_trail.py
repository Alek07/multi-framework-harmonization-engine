"""UCM-13 - The invariant, read off the audit log rather than off the return value.

If the claim is "the RAG only widens coverage, never restricts it in silence",
then the log alone has to be enough to check it: every capability accounted for in
every zone, the candidates before the pass next to the ones after it, and every
candidate a lens set aside written down with the axis that set it aside.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.repository import AuditRepository
from app.audit.schemas import AuditActor, AuditEventType, AuditStage
from app.audit.service import AuditService
from app.catalog.schemas import Catalog, Jurisdiction
from app.engine.schemas import ProfileResolution
from app.retrieval.schemas import PayloadFilter
from app.retrieval.service import RetrievalService
from app.retrieval.trail import trail_for_retrieval
from tests.retrieval.conftest import FakeIndex


@pytest.fixture
def service(fake_index: FakeIndex) -> RetrievalService:
    return RetrievalService(index=fake_index)


def test_the_pass_is_engine_authored_and_never_anonymous(
    service: RetrievalService, resolution_a: ProfileResolution
) -> None:
    """The retriever offers; it does not decide. Its entries are the engine's."""
    entries = trail_for_retrieval(service.retrieve_profile(resolution_a), uuid4())

    assert entries
    for entry in entries:
        assert entry.actor is AuditActor.ENGINE
        assert entry.actor_ref == "engine.retrieval"
        assert entry.stage is AuditStage.RETRIEVAL
        assert entry.decision.strip()
        assert entry.rationale.strip()


def test_every_capability_leaves_a_mark_in_every_zone(
    service: RetrievalService, resolution_a: ProfileResolution, catalog: Catalog
) -> None:
    entries = trail_for_retrieval(service.retrieve_profile(resolution_a), uuid4())
    retrieved = [e for e in entries if e.event_type is AuditEventType.CANDIDATES_RETRIEVED]

    for zone in resolution_a.zones:
        in_zone = {e.capability_id for e in retrieved if e.zone_id == zone.zone.zone_id}
        assert in_zone == catalog.capability_ids


def test_the_log_shows_coverage_only_ever_growing(
    service: RetrievalService, resolution_a: ProfileResolution
) -> None:
    """The measurable form of the invariant, on the record itself."""
    entries = trail_for_retrieval(service.retrieve_profile(resolution_a), uuid4())

    for entry in entries:
        if entry.event_type is not AuditEventType.CANDIDATES_RETRIEVED:
            continue
        before = entry.payload["catalog_control_ids"]
        after = entry.payload["offered_control_ids"]

        assert set(after) >= set(before)
        assert len(after) >= len(before)


def test_each_stage_entry_closes_its_zone_with_what_it_accounted_for(
    service: RetrievalService, resolution_a: ProfileResolution, catalog: Catalog
) -> None:
    entries = trail_for_retrieval(service.retrieve_profile(resolution_a), uuid4())
    completed = [e for e in entries if e.event_type is AuditEventType.STAGE_COMPLETED]

    assert len(completed) == len(resolution_a.zones)
    for entry in completed:
        assert entry.payload["capabilities"] == len(catalog.capabilities)
        assert set(entry.payload["capability_ids"]) == catalog.capability_ids
        assert entry.payload["lens_active"] is False


def test_what_a_lens_set_aside_is_recoverable_from_the_log_alone(
    service: RetrievalService, resolution_a: ProfileResolution
) -> None:
    lens = PayloadFilter(jurisdictions=[Jurisdiction.EU], rationale="lectura europea")
    retrieval = service.retrieve_profile(resolution_a, lens)
    entries = trail_for_retrieval(retrieval, uuid4())
    set_aside = [e for e in entries if e.event_type is AuditEventType.CANDIDATE_SET_ASIDE]

    assert len(set_aside) == len(retrieval.set_aside)
    for entry in set_aside:
        assert entry.control_id
        assert entry.payload["excluded_by"]
        assert entry.payload["score"] is not None


def test_the_versions_say_which_vectors_answered(
    service: RetrievalService, resolution_a: ProfileResolution, catalog: Catalog
) -> None:
    retrieval = service.retrieve_profile(resolution_a)
    entries = trail_for_retrieval(retrieval, uuid4())

    for entry in entries:
        assert entry.versions["catalog"] == catalog.catalog_version
        assert entry.versions["embedding_model"]
        # The collection name carries the catalog digest: the log therefore says
        # the vectors were built from this exact catalog, not merely that this
        # catalog version was configured.
        assert entry.versions["collection"] == retrieval.provenance.collection
        assert retrieval.provenance.catalog_digest in entry.versions["collection"]


def test_the_entries_all_belong_to_one_run(
    service: RetrievalService, resolution_a: ProfileResolution
) -> None:
    run_id = uuid4()
    entries = trail_for_retrieval(service.retrieve_profile(resolution_a), run_id)

    assert {e.run_id for e in entries} == {run_id}
    assert {e.profile_id for e in entries} == {resolution_a.profile_id}


async def test_the_pass_is_appendable_next_to_the_core_run(
    db: AsyncSession, service: RetrievalService, resolution_a: ProfileResolution
) -> None:
    """The new stage is not a parallel record: it joins the same chained ledger."""
    audit = AuditService(AuditRepository(db))
    run_id = uuid4()
    retrieval = service.retrieve_profile(resolution_a)

    recorded = await audit.record_retrieval(retrieval, run_id)
    verification = await audit.verify_run(run_id)

    assert len(recorded) == len(trail_for_retrieval(retrieval, run_id))
    assert {e.stage for e in recorded} == {AuditStage.RETRIEVAL}
    assert verification.valid is True
