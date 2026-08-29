"""UCM-13 - The RAG against the real Qdrant and the real e5-base. `uv run pytest -m rag`.

Deselected by default because it needs the container up and the ~1.1 GB model on
disk — the rest of the suite must stay runnable on any machine, offline. What it
checks is what a fake ranker cannot check, because it is about the retrieval
itself:

* the collection really is built from the catalog, and rebuilding it is idempotent;
* the same query returns the same controls in the same order, twice (invariant 3);
* the cross-lingual claim holds: a capability written in Spanish pulls controls
  whose titles are the frameworks' English;
* a payload filter narrows the *view* and hands back everything it set aside;
* over both hand-written profiles, no catalog candidate is ever lost.

The last one is the ticket's invariant measured end to end, against the real
index rather than a stand-in.
"""

from __future__ import annotations

import pytest

from app.assets.schemas import AssetProfile
from app.catalog.schemas import Catalog, Framework, Jurisdiction
from app.engine.schemas import ProfileResolution
from app.retrieval.embeddings import capability_text
from app.retrieval.index import CatalogIndex
from app.retrieval.schemas import FilterAxis, PayloadFilter
from app.retrieval.service import RetrievalService

pytestmark = pytest.mark.rag


@pytest.fixture(scope="module")
def index() -> CatalogIndex:
    """The shipped index, populated against the running Qdrant."""
    built = CatalogIndex()
    built.ensure()
    return built


@pytest.fixture(scope="module")
def service(index: CatalogIndex) -> RetrievalService:
    return RetrievalService(index=index)


def test_the_collection_holds_the_whole_catalog(index: CatalogIndex, catalog: Catalog) -> None:
    stored = index.client.count(index.collection, exact=True).count

    assert stored == len(catalog.controls)
    assert index.collection.startswith("catalog_v0_4_0_")


def test_populating_twice_changes_nothing(index: CatalogIndex, catalog: Catalog) -> None:
    """Point IDs are deterministic, so a rebuild overwrites instead of duplicating."""
    assert index.ensure() is False

    index.ensure(force=True)

    assert index.client.count(index.collection, exact=True).count == len(catalog.controls)


def test_the_same_query_returns_the_same_controls_in_the_same_order(
    index: CatalogIndex, catalog: Catalog
) -> None:
    capability = next(c for c in catalog.capabilities if c.id == "CAP-PR-MFA")
    query = capability_text(capability)

    first = index.search(query, limit=10)
    second = index.search(query, limit=10)

    assert [hit.control_id for hit in first] == [hit.control_id for hit in second]
    assert [round(hit.score, 6) for hit in first] == [round(hit.score, 6) for hit in second]


def test_a_spanish_capability_finds_english_titled_controls(
    index: CatalogIndex, catalog: Catalog
) -> None:
    """The reason the model is multilingual: the query and the passage differ in language."""
    capability = next(c for c in catalog.capabilities if c.id == "CAP-PR-MFA")

    hits = index.search(capability_text(capability), limit=5)
    mapped = {m.control_id for m in catalog.mappings_for(capability.id)}

    assert hits
    assert mapped & {hit.control_id for hit in hits}, (
        "the controls the author mapped to MFA should be among the nearest neighbours: "
        f"{[(h.control_id, round(h.score, 3)) for h in hits]}"
    )


def test_the_pass_never_costs_a_catalog_candidate(
    service: RetrievalService, resolution_a: ProfileResolution, resolution_b: ProfileResolution
) -> None:
    """The ticket's invariant, end to end, over both hand-written profiles."""
    for resolution in (resolution_a, resolution_b):
        retrieval = service.retrieve_profile(resolution)
        for zone in resolution.zones:
            widened = retrieval.zone(zone.zone.zone_id)
            for capability in zone.capabilities:
                before = [option.control_id for option in capability.options]
                after = widened.capability(capability.capability.id).offered_control_ids

                assert set(after) >= set(before)


def test_retrieval_actually_widens_something(
    service: RetrievalService, resolution_a: ProfileResolution
) -> None:
    """A pass that suggested nothing would satisfy the invariant and be useless."""
    retrieval = service.retrieve_profile(resolution_a)

    assert retrieval.suggestions > 0
    assert retrieval.zones[0].widened_capability_ids


def test_a_jurisdiction_lens_narrows_the_view_and_reports_what_it_hid(
    service: RetrievalService, resolution_a: ProfileResolution
) -> None:
    lens = PayloadFilter(jurisdictions=[Jurisdiction.EU], rationale="lectura europea (UCM-17)")
    retrieval = service.retrieve_profile(resolution_a, lens)

    assert retrieval.set_aside
    for zone in retrieval.zones:
        for capability in zone.capabilities:
            assert all(hit.jurisdiction is Jurisdiction.EU for hit in capability.retrieved)
            assert all(c.jurisdiction is not Jurisdiction.EU for c in capability.set_aside)


def test_the_sectoral_applicability_sets_out_of_scope_norms_aside(
    service: RetrievalService, resolution_a: ProfileResolution
) -> None:
    """UCM-52 end to end: an energy asset sets the maritime (IMO) norms aside.

    Against the real index and the real nested `should`/`is_empty` filter: the
    out-of-sector norms come back on the sector axis, the transversal controls are
    never excluded, and nothing set aside is still offered as a live suggestion.
    """
    retrieval = service.retrieve_profile(resolution_a)

    sector_aside = [c for c in retrieval.set_aside if FilterAxis.SECTOR in c.excluded_by]
    assert sector_aside, "IMO's maritime controls are out of the energy sector"
    assert all(c.framework is Framework.IMO for c in sector_aside)

    shown = {
        hit.control_id
        for zone in retrieval.zones
        for capability in zone.capabilities
        for hit in capability.widening
    }
    assert not (shown & {c.control_id for c in sector_aside})


def test_the_lens_does_not_touch_the_profile_it_reads(
    service: RetrievalService, resolution_a: ProfileResolution, profile_a: AssetProfile
) -> None:
    before = resolution_a.model_dump_json()
    service.retrieve_profile(resolution_a, PayloadFilter(jurisdictions=[Jurisdiction.EU]))

    assert resolution_a.model_dump_json() == before
    assert resolution_a.profile_id == profile_a.id
