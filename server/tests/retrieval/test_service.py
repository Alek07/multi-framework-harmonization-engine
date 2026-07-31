"""UCM-13 - The measured invariant: the RAG widens, and never restricts in silence.

Everything here is a check on that one sentence. The stand-in ranker
(`conftest.FakeIndex`) is irrelevant to what is being asserted: whichever controls
come back, the catalog's own candidates have to survive untouched, a suggestion
has to be labelled as a suggestion, a declared lens has to hand back what it set
aside, and a capability with nothing at all has to end as an explicit gap.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.catalog.schemas import Catalog, Jurisdiction, MappingType
from app.core.config import settings
from app.engine.schemas import (
    CapabilityResolution,
    GapKind,
    ProfileResolution,
)
from app.retrieval.schemas import (
    CapabilityRetrieval,
    PayloadFilter,
    RetrievalRelation,
    RetrievedControl,
)
from app.retrieval.service import RetrievalService
from tests.retrieval.conftest import FakeIndex


@pytest.fixture
def service(fake_index: FakeIndex) -> RetrievalService:
    return RetrievalService(index=fake_index)


# --- the invariant ------------------------------------------------------------


def test_no_catalog_candidate_is_lost_in_the_pass(
    service: RetrievalService, resolution_a: ProfileResolution
) -> None:
    """What the deterministic core offered is carried through, control by control."""
    retrieval = service.retrieve_profile(resolution_a)

    for zone in resolution_a.zones:
        retrieved_zone = retrieval.zone(zone.zone.zone_id)
        for capability in zone.capabilities:
            widened = retrieved_zone.capability(capability.capability.id)
            offered_before = [option.control_id for option in capability.options]

            assert widened.catalog_control_ids == offered_before
            assert set(widened.offered_control_ids) >= set(offered_before)
            assert len(widened.offered_control_ids) >= len(offered_before)


def test_every_capability_of_every_zone_is_accounted_for(
    service: RetrievalService, resolution_a: ProfileResolution, catalog: Catalog
) -> None:
    """No capability may quietly fail to appear in the result (invariant 2)."""
    retrieval = service.retrieve_profile(resolution_a)

    assert [z.zone.zone_id for z in retrieval.zones] == [
        z.zone.zone_id for z in resolution_a.zones
    ]
    for zone in retrieval.zones:
        assert {c.capability_id for c in zone.capabilities} == catalog.capability_ids


def test_a_suggestion_is_labelled_a_suggestion_and_carries_no_coverage(
    service: RetrievalService, resolution_a: ProfileResolution
) -> None:
    """An embedding distance is not evidence of equivalence, and the type says so."""
    retrieval = service.retrieve_profile(resolution_a)
    suggestions = [s for z in retrieval.zones for c in z.capabilities for s in c.widening]

    assert suggestions, "the fake ranker should surface at least one widening candidate"
    for zone in retrieval.zones:
        for capability in zone.capabilities:
            for hit in capability.widening:
                assert hit.control_id not in capability.catalog_control_ids
            for hit in capability.confirmations:
                assert hit.control_id in capability.catalog_control_ids

    # `RetrievedControl` has no coverage weight to give: coverage stays the
    # deterministic core's arithmetic, computed from authored mappings only.
    assert "coverage_weight" not in RetrievedControl.model_fields


def test_the_pass_leaves_the_core_resolution_untouched(
    service: RetrievalService, resolution_a: ProfileResolution
) -> None:
    before = resolution_a.model_dump_json()
    service.retrieve_profile(resolution_a)

    assert resolution_a.model_dump_json() == before


def test_the_same_inputs_retrieve_the_same_candidates(
    service: RetrievalService, resolution_a: ProfileResolution
) -> None:
    first = service.retrieve_profile(resolution_a)
    second = service.retrieve_profile(resolution_a)

    assert first.model_dump_json() == second.model_dump_json()


# --- the lens -----------------------------------------------------------------


def test_a_lens_hands_back_everything_it_set_aside(
    service: RetrievalService, resolution_a: ProfileResolution
) -> None:
    lens = PayloadFilter(jurisdictions=[Jurisdiction.EU], rationale="lectura europea")
    retrieval = service.retrieve_profile(resolution_a, lens)

    for zone in retrieval.zones:
        for capability in zone.capabilities:
            for hit in capability.retrieved:
                assert hit.jurisdiction is Jurisdiction.EU
            for candidate in capability.set_aside:
                assert candidate.jurisdiction is not Jurisdiction.EU
                assert candidate.excluded_by
                assert candidate.rationale.strip()

    assert retrieval.set_aside, "an EU lens over a mostly-US catalog must set candidates aside"


def test_a_lens_narrows_the_view_and_never_the_baseline(
    service: RetrievalService, resolution_a: ProfileResolution
) -> None:
    """The strongest form of the invariant: filtering cannot cost a catalog candidate."""
    unfiltered = service.retrieve_profile(resolution_a)
    filtered = service.retrieve_profile(
        resolution_a, PayloadFilter(mapping_types=[MappingType.TOTAL])
    )

    for zone in unfiltered.zones:
        other = filtered.zone(zone.zone.zone_id)
        for capability in zone.capabilities:
            assert (
                other.capability(capability.capability_id).catalog_control_ids
                == capability.catalog_control_ids
            )


def test_without_a_lens_nothing_is_set_aside(
    service: RetrievalService, resolution_a: ProfileResolution
) -> None:
    """The engine does not filter on its own initiative, so there is nothing to report."""
    retrieval = service.retrieve_profile(resolution_a)

    assert retrieval.set_aside == []
    assert retrieval.provenance.payload_filter.is_active is False
    assert all(query_filter is None for _, _, query_filter in service.index.queries)  # type: ignore[attr-defined]


def test_the_query_reserves_room_for_the_extra_candidates(
    service: RetrievalService, resolution_a: ProfileResolution
) -> None:
    """`RAG_TOP_K` is a floor on suggestions, not a budget the catalog eats into."""
    service.retrieve_profile(resolution_a)

    zone = resolution_a.zones[0]
    by_capability = {c.capability.id: len(c.options) for c in zone.capabilities}
    asked = {limit for _, limit, _ in service.index.queries}  # type: ignore[attr-defined]

    assert asked == {settings.RAG_TOP_K + count for count in by_capability.values()}


# --- gaps ---------------------------------------------------------------------


def test_a_capability_with_no_candidate_at_all_becomes_an_explicit_gap(
    empty_index: FakeIndex, catalog: Catalog
) -> None:
    capability = CapabilityResolution(
        capability=sorted(catalog.capabilities, key=lambda c: c.id)[0],
        zone_id="Z-TEST",
        options=[],
        coverage=0.0,
        has_full_mechanism=False,
    )

    result = RetrievalService(index=empty_index).retrieve_capability(capability)

    assert result.gap is not None
    assert result.gap.kind is GapKind.NO_CANDIDATE
    assert result.gap.residual == 1.0
    assert result.offered_control_ids == []
    assert "sigue exigida" in result.gap.rationale


def test_a_silent_omission_cannot_even_be_represented(catalog: Catalog) -> None:
    """No candidates and no declared gap is not a bug to catch later — it is unbuildable."""
    with pytest.raises(ValidationError, match="silent omission"):
        CapabilityRetrieval(
            capability_id="CAP-PR-MFA",
            capability_name="Autenticación multifactor",
            zone_id="Z-TEST",
            catalog_control_ids=[],
            retrieved=[],
            gap=None,
            rationale="…",
        )


def test_a_mislabelled_hit_cannot_be_represented(catalog: Catalog) -> None:
    """"Widens" must mean the catalog does not already map it. The model enforces it."""
    control = catalog.controls[0]
    hit = RetrievedControl(
        control=control,
        score=0.9,
        relation=RetrievalRelation.WIDENS,
        rationale="…",
    )

    with pytest.raises(ValidationError, match="already maps it"):
        CapabilityRetrieval(
            capability_id="CAP-GOV-RISK",
            capability_name="Gestión del riesgo",
            zone_id="Z-TEST",
            catalog_control_ids=[control.id],
            retrieved=[hit],
            rationale="…",
        )


# --- provenance ---------------------------------------------------------------


def test_the_provenance_pins_the_vectors_that_answered(
    service: RetrievalService, resolution_a: ProfileResolution, catalog: Catalog
) -> None:
    retrieval = service.retrieve_profile(resolution_a)
    provenance = retrieval.provenance

    assert provenance.embedding_model == settings.EMBEDDING_MODEL
    assert provenance.catalog_version == catalog.catalog_version
    assert provenance.catalog_digest in provenance.collection
    assert provenance.indexed_controls == len(catalog.controls)
    assert provenance.top_k == settings.RAG_TOP_K


def test_it_refuses_to_widen_a_resolution_from_another_catalog(
    service: RetrievalService, resolution_a: ProfileResolution
) -> None:
    stale = resolution_a.model_copy(update={"catalog_version": "0.0.9"})

    with pytest.raises(ValueError, match="catalog 0.0.9"):
        service.retrieve_profile(stale)
