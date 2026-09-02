from __future__ import annotations

from collections import Counter

import pytest
from pydantic import ValidationError

from app.catalog.schemas import Catalog, Jurisdiction, MappingType
from app.core.config import settings
from app.engine.schemas import (
    CapabilityResolution,
    GapKind,
    GatingOutcome,
    ProfileGating,
    ProfileResolution,
)
from app.retrieval.schemas import (
    CapabilityRetrieval,
    FilterAxis,
    GatingAnnotation,
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


def test_the_engine_applies_the_zones_sectoral_applicability(
    service: RetrievalService, resolution_a: ProfileResolution
) -> None:
    """UCM-52: sectoral applicability (UCM-47) is the engine's own lens.

    PROFILE-A operates in energy, so an out-of-sector norm — IMO governs shipping —
    is not suggested as if it applied. That is a determination, not a silent
    restriction: it comes back set aside on the sector axis, with its reason, and
    is not among the suggestions the engine still shows.
    """
    retrieval = service.retrieve_profile(resolution_a)

    # The main query carries the sector filter — not the wire-level `None` of an
    # unfiltered pass — and the applicability it applies is reported, never silent.
    assert any(query_filter is not None for _, _, query_filter in service.index.queries)  # type: ignore[attr-defined]

    sector_aside = [c for c in retrieval.set_aside if FilterAxis.SECTOR in c.excluded_by]
    assert sector_aside, "an energy asset must set the maritime (IMO) norms aside"
    for candidate in sector_aside:
        assert candidate.rationale.strip()

    shown = {
        hit.control_id
        for zone in retrieval.zones
        for capability in zone.capabilities
        for hit in capability.widening
    }
    assert not (shown & {c.control_id for c in sector_aside}), (
        "a norm set aside by sector must not also be offered as a live suggestion"
    )


def test_a_zone_without_declared_sectors_is_not_filtered(
    service: RetrievalService, resolution_a: ProfileResolution
) -> None:
    """Unknown sectors exclude nothing (UCM-47): no premise, no filter, no set_aside."""
    sectorless = resolution_a.model_copy(
        update={
            "zones": [
                zone.model_copy(update={"zone": zone.zone.model_copy(update={"sectors": []})})
                for zone in resolution_a.zones
            ]
        }
    )
    retrieval = service.retrieve_profile(sectorless)

    assert retrieval.set_aside == []
    assert retrieval.provenance.payload_filter.is_active is False
    assert all(query_filter is None for _, _, query_filter in service.index.queries)  # type: ignore[attr-defined]


def test_the_query_reserves_room_for_the_extra_candidates(
    service: RetrievalService, resolution_a: ProfileResolution
) -> None:
    """The depth is asked on top of the catalog's own candidates, not out of them."""
    service.retrieve_profile(resolution_a)

    zone = resolution_a.zones[0]
    by_capability = {c.capability.id: len(c.options) for c in zone.capabilities}
    asked = {limit for _, limit, _ in service.index.queries}  # type: ignore[attr-defined]

    assert asked == {
        settings.RAG_RETRIEVAL_DEPTH + count for count in by_capability.values()
    }


def test_every_answered_capability_declares_the_cut_that_bounded_it(
    service: RetrievalService, resolution_a: ProfileResolution
) -> None:
    """Acceptance (UCM-54): the retriever stops being the one stage with no rule."""
    retrieval = service.retrieve_profile(resolution_a)

    for zone in retrieval.zones:
        for capability in zone.capabilities:
            if not capability.retrieved:
                continue
            cut = capability.cut
            assert cut is not None, f"{capability.capability_id} shows candidates with no cut"
            assert cut.policy.version
            assert cut.retained + cut.dropped == cut.evaluated
            assert cut.retained >= min(cut.policy.floor, cut.evaluated)
            assert cut.retained <= cut.policy.ceiling
            if cut.dropped:
                assert cut.first_dropped is not None
                assert cut.first_dropped.rationale.strip()


def test_the_cut_never_reaches_the_catalogs_own_candidates(
    service: RetrievalService, resolution_a: ProfileResolution
) -> None:
    """The rule bounds suggestions. A confirmation is never handed to it."""
    retrieval = service.retrieve_profile(resolution_a)

    for zone in retrieval.zones:
        for capability in zone.capabilities:
            offered = set(capability.offered_control_ids)
            assert set(capability.catalog_control_ids) <= offered
            cut = capability.cut
            if cut is None:
                continue
            dropped_ids = {d.control_id for d in cut.displaced}
            assert not (dropped_ids & set(capability.catalog_control_ids))


def test_no_framework_holds_more_than_its_share_of_the_suggestions(
    service: RetrievalService, resolution_a: ProfileResolution
) -> None:
    """The cap is the half of the rule that changes *which* candidates are shown."""
    retrieval = service.retrieve_profile(resolution_a)

    for zone in retrieval.zones:
        for capability in zone.capabilities:
            cut = capability.cut
            if cut is None:
                continue
            held = Counter(hit.framework for hit in capability.widening)
            over = {f: n for f, n in held.items() if n > settings.RAG_FRAMEWORK_CAP}
            # Over the cap only where it yielded to keep the floor, and the report says so.
            assert not over or cut.cap_yielded > 0, (
                f"{capability.capability_id} shows {held} with a cap of "
                f"{settings.RAG_FRAMEWORK_CAP} and no yield on record"
            )


def test_what_the_cut_displaced_is_never_also_shown(
    service: RetrievalService, resolution_a: ProfileResolution
) -> None:
    """Displaced means displaced: the report and the list cannot both claim it."""
    retrieval = service.retrieve_profile(resolution_a)

    for zone in retrieval.zones:
        for capability in zone.capabilities:
            if capability.cut is None:
                continue
            shown = {hit.control_id for hit in capability.retrieved}
            assert not (shown & {d.control_id for d in capability.cut.displaced})


def test_the_cut_cannot_turn_a_covered_capability_into_a_gap(
    service: RetrievalService, resolution_a: ProfileResolution
) -> None:
    """Bounding a ranking may never cost coverage — the invariant, at this seam."""
    retrieval = service.retrieve_profile(resolution_a)

    for zone in retrieval.zones:
        for capability in zone.capabilities:
            if capability.cut is not None and capability.cut.evaluated:
                assert capability.gap is None or not capability.catalog_control_ids


# --- gating visible in the suggestions (UCM-52) -------------------------------


def test_no_suggestion_contradicts_a_gating_exclusion_in_silence(
    service: RetrievalService, resolution_a: ProfileResolution, gating_a: ProfileGating
) -> None:
    """Acceptance: a suggestion for a mechanism gating ruled out of the zone says so.

    Before UCM-52 the engine could exclude a mechanism in a zone and suggest the
    same control two lines below. Now every such suggestion is annotated with the
    exclusion — shown marked, not hidden — and never contradicts the engine.
    """
    retrieval = service.retrieve_profile(resolution_a, gating=gating_a)

    for zone in retrieval.zones:
        gated = {d.control_id: d for d in gating_a.zone(zone.zone.zone_id).decisions}
        for capability in zone.capabilities:
            for hit in capability.widening:
                if hit.control_id in gated:
                    assert hit.gated_out is not None, (
                        f"{hit.control_id} is gated out of {zone.zone.zone_id} but suggested "
                        "without saying so"
                    )
                    assert hit.gated_out.zone_id == zone.zone.zone_id
                    assert hit.gated_out.rule_id == gated[hit.control_id].rule_id
                    assert "gating" in hit.rationale.lower()
                else:
                    assert hit.gated_out is None


def test_the_same_capability_reads_differently_in_zones_of_different_nature(
    service: RetrievalService,
    resolution_a: ProfileResolution,
    gating_a: ProfileGating,
    resolution_b: ProfileResolution,
    gating_b: ProfileGating,
) -> None:
    """Acceptance: nature changes the suggestions' justification, deterministically.

    A mechanism that needs a general-purpose OS is gated out of PROFILE-A's OT
    corridor (which has none) and applicable in PROFILE-B's engineering station
    (which does). The same suggestion therefore carries a gating exclusion in one
    zone's nature and not the other's — distinct sets, each with its reason.
    """
    ret_a = service.retrieve_profile(resolution_a, gating=gating_a)
    ret_b = service.retrieve_profile(resolution_b, gating=gating_b)

    def gated_widenings(retrieval: object) -> dict[tuple[str, str], bool]:
        return {
            (capability.capability_id, hit.control_id): hit.gated_out is not None
            for zone in retrieval.zones  # type: ignore[attr-defined]
            for capability in zone.capabilities
            for hit in capability.widening
        }

    a, b = gated_widenings(ret_a), gated_widenings(ret_b)
    differing = [key for key in a.keys() & b.keys() if a[key] != b[key]]

    assert differing, (
        "at least one suggestion must be gated out under one zone's nature and applicable "
        "under the other's — the asset-aware difference the ticket asks for"
    )


def test_a_gated_suggestion_is_annotated_not_hidden(
    service: RetrievalService, resolution_a: ProfileResolution
) -> None:
    """The mechanism the ticket names: a suggestion gating excludes stays offered, marked."""
    zone = resolution_a.zones[0]
    capability = zone.capabilities[0]

    plain = service.retrieve_capability(capability)
    assert plain.widening, "the fake ranker should surface a widening to annotate"
    target = plain.widening[0].control_id

    annotation = GatingAnnotation(
        zone_id=zone.zone.zone_id,
        outcome=GatingOutcome.NOT_APPLICABLE,
        rule_id="TEST-RULE",
        rationale="regla de prueba",
        evidence=["premisa observada"],
    )
    marked = service.retrieve_capability(capability, gated={target: annotation})

    hit = next(h for h in marked.widening if h.control_id == target)
    assert hit.gated_out == annotation
    assert target in marked.offered_control_ids  # annotated, never removed from the list
    assert "gating" in hit.rationale.lower()


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
