"""The facts: the order on screen, what may be cited, what is said anyway.

The explanation layer is only as honest as the sheet it reads. Three properties make
the rest checkable: candidates arrive in the engine's order, a candidate's citable
evidence matches what it actually has (a suggestion has a similarity and no mapping;
a mapping has a type, a weight and a provenance), and every candidate carries
deterministic text before any model is asked anything.
"""

from __future__ import annotations

import pytest

from app.catalog.schemas import ProvenanceSource
from app.engine.schemas import ProfileResolution
from app.explain.evidence import fact_sheet, facts_for
from app.explain.schemas import CandidateOrigin, EvidenceKey
from tests.explain.conftest import Case


def test_the_candidates_keep_the_order_they_are_offered_in(case: Case) -> None:
    """Catalog candidates first, in the core's order, then the RAG suggestions."""
    facts = case.facts

    assert facts.offered_control_ids == case.retrieval.offered_control_ids
    origins = [candidate.origin for candidate in facts.candidates]
    catalog = [i for i, origin in enumerate(origins) if origin is CandidateOrigin.CATALOG]
    suggested = [i for i, origin in enumerate(origins) if origin is CandidateOrigin.RETRIEVAL]

    assert catalog and suggested
    assert max(catalog) < min(suggested)


def test_a_catalog_candidate_cites_its_mapping_and_a_suggestion_cannot(case: Case) -> None:
    for candidate in case.facts.candidates:
        if candidate.origin is CandidateOrigin.CATALOG:
            assert candidate.mapping is not None
            assert EvidenceKey.CATALOG_MAPPING in candidate.allowed
            assert EvidenceKey.COVERAGE_WEIGHT in candidate.allowed
        else:
            # The whole point of the distinction: an embedding neighbour has no
            # authored mapping to this capability, so it has none to cite.
            assert candidate.mapping is None
            assert EvidenceKey.CATALOG_MAPPING not in candidate.allowed
            assert EvidenceKey.SIMILARITY in candidate.allowed


def test_similarity_is_only_citable_where_there_is_one(case: Case) -> None:
    for candidate in case.facts.candidates:
        has_score = candidate.score is not None
        assert (EvidenceKey.SIMILARITY in candidate.allowed) is has_score


def test_the_zone_is_citable_only_when_it_was_given(case: Case) -> None:
    with_zone = facts_for(case.resolution, case.retrieval, case.zone)
    without_zone = facts_for(case.resolution, case.retrieval)

    assert all(EvidenceKey.ZONE_CONTEXT in c.allowed for c in with_zone.candidates)
    assert all(EvidenceKey.ZONE_CONTEXT not in c.allowed for c in without_zone.candidates)


def test_every_candidate_has_deterministic_text_before_any_model_runs(case: Case) -> None:
    """The fallback is what makes the layer unable to leave a candidate bare."""
    for candidate in case.facts.candidates:
        assert candidate.fallback.strip()
        assert candidate.official_id in candidate.fallback or "Sugerencia" in candidate.fallback


def test_the_sheet_lists_every_candidate_with_its_citable_evidence(case: Case) -> None:
    sheet = fact_sheet(case.facts)

    assert case.resolution.capability.name in sheet
    assert case.zone.zone_id in sheet
    for candidate in case.facts.candidates:
        assert f"control_id={candidate.control_id}" in sheet
        assert candidate.control.paraphrased_description in sheet
    for key in case.facts.candidates[0].allowed:
        assert key.value in sheet


def test_the_sheet_is_the_same_for_the_same_inputs(case: Case) -> None:
    """A prompt that varied run to run would make the prose irreproducible."""
    assert fact_sheet(case.facts) == fact_sheet(case.facts)


def test_the_model_is_never_asked_to_translate_an_identifier(case: Case) -> None:
    """Sheet 1.0.0 printed `author_judgment`; the 7B rendered it "autorización
    internacional", promoting the catalog author's judgement to an official
    authorisation. The fix is to hand it the Spanish label, so the raw enum values
    must not appear in the sheet at all."""
    sheet = fact_sheet(case.facts)

    for identifier in ("author_judgment", "official_crosswalk", "INTL", "not_applicable"):
        assert identifier not in sheet


def test_an_author_judgment_says_it_is_not_a_crosswalk(case: Case) -> None:
    """The distinction the catalog is built on has to survive into the prompt."""
    authored = [
        candidate
        for candidate in case.facts.candidates
        if candidate.mapping is not None
        and candidate.mapping.provenance.source is ProvenanceSource.AUTHOR_JUDGMENT
    ]
    assert authored, "profile A should offer at least one author-judged mapping"

    sheet = fact_sheet(case.facts)
    assert "juicio del autor del catálogo (no es un crosswalk oficial)" in sheet
    for candidate in authored:
        assert "juicio del autor" in candidate.fallback


def test_a_gap_has_nothing_to_explain(gap_case: Case) -> None:
    assert gap_case.facts.candidates == ()
    assert gap_case.retrieval.gap is not None


def test_it_refuses_to_mix_two_capabilities(
    case: Case, resolution_a: ProfileResolution
) -> None:
    """Fluent prose written from another capability's facts is the worst failure."""
    other = next(
        capability
        for capability in resolution_a.zones[0].capabilities
        if capability.capability.id != case.resolution.capability.id
    )

    with pytest.raises(ValueError, match="the resolution is for"):
        facts_for(other, case.retrieval, case.zone)
