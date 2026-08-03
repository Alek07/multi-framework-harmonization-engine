"""UCM-14 - The contract: an explanation layer that decided is not representable.

The service is one implementation; the type is the promise. Everything here is a
statement about `CapabilityExplanations` that holds however the prose was
produced — including by code written after this ticket. If a future caller tried
to hand the operator a reordered candidate list with a model's ranking behind it,
it would fail to build.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.catalog.schemas import Framework, Jurisdiction
from app.explain.schemas import (
    CandidateExplanation,
    CandidateOrigin,
    CapabilityExplanations,
    EvidenceKey,
    ExplanationProvenance,
    ExplanationStatus,
)

PROVENANCE = ExplanationProvenance(
    model="qwen2.5:7b-instruct-q4_K_M",
    prompt_version="0.2.0",
    sheet_template_version="1.1.0",
    temperature=0.0,
    seed=42,
    top_p=1.0,
    num_predict=2048,
    catalog_version="0.1.0",
)


def explanation(
    control_id: str, status: ExplanationStatus = ExplanationStatus.GENERATED
) -> CandidateExplanation:
    return CandidateExplanation(
        control_id=control_id,
        official_id="PR.AA-03",
        framework=Framework.CSF,
        jurisdiction=Jurisdiction.US,
        origin=CandidateOrigin.CATALOG,
        text="El catálogo lo mapea a esta capacidad.",
        status=status,
        basis=[EvidenceKey.CATALOG_MAPPING] if status is ExplanationStatus.GENERATED else [],
        notice=None if status is not ExplanationStatus.WITHHELD else "retenida",
    )


def capability(
    offered: list[str], explanations: list[CandidateExplanation]
) -> CapabilityExplanations:
    return CapabilityExplanations(
        capability_id="CAP-PR-MFA",
        capability_name="Autenticación multifactor",
        zone_id="Z-TEST",
        offered_control_ids=offered,
        explanations=explanations,
        provenance=PROVENANCE,
    )


# --- the bijection ------------------------------------------------------------


def test_a_dropped_candidate_cannot_be_represented() -> None:
    with pytest.raises(ValidationError, match="may not add, drop or reorder"):
        capability(["CTL-A", "CTL-B"], [explanation("CTL-A")])


def test_an_added_candidate_cannot_be_represented() -> None:
    with pytest.raises(ValidationError, match="may not add, drop or reorder"):
        capability(["CTL-A"], [explanation("CTL-A"), explanation("CTL-B")])


def test_a_reordered_candidate_list_cannot_be_represented() -> None:
    """Answering "best first" is ranking, and ranking is not this layer's to do."""
    with pytest.raises(ValidationError, match="may not add, drop or reorder"):
        capability(["CTL-A", "CTL-B"], [explanation("CTL-B"), explanation("CTL-A")])


def test_the_offered_list_and_the_explanations_agree() -> None:
    result = capability(["CTL-A", "CTL-B"], [explanation("CTL-A"), explanation("CTL-B")])

    assert [e.control_id for e in result.explanations] == result.offered_control_ids
    assert result.presentational is True


# --- nothing to influence a decision with -------------------------------------


def test_an_explanation_carries_no_number_at_all() -> None:
    """No score, no weight, no rank, no tier: there is nothing here to rank with."""
    forbidden = {"score", "coverage_weight", "coverage", "rank", "ranking", "priority", "tier"}

    assert forbidden.isdisjoint(CandidateExplanation.model_fields)


def test_generated_prose_must_cite_something_checkable() -> None:
    with pytest.raises(ValidationError, match="leans on nothing checkable"):
        CandidateExplanation(
            control_id="CTL-A",
            official_id="PR.AA-03",
            framework=Framework.CSF,
            jurisdiction=Jurisdiction.US,
            origin=CandidateOrigin.CATALOG,
            text="Aparece por su relación con la capacidad.",
            status=ExplanationStatus.GENERATED,
            basis=[],
        )


def test_only_generated_prose_carries_a_basis() -> None:
    with pytest.raises(ValidationError, match="only generated prose carries a basis"):
        CandidateExplanation(
            control_id="CTL-A",
            official_id="PR.AA-03",
            framework=Framework.CSF,
            jurisdiction=Jurisdiction.US,
            origin=CandidateOrigin.CATALOG,
            text="El catálogo lo mapea a esta capacidad.",
            status=ExplanationStatus.UNAVAILABLE,
            basis=[EvidenceKey.CATALOG_MAPPING],
        )


def test_withholding_in_silence_cannot_be_represented() -> None:
    with pytest.raises(ValidationError, match="withholds the model's text without saying so"):
        CandidateExplanation(
            control_id="CTL-A",
            official_id="PR.AA-03",
            framework=Framework.CSF,
            jurisdiction=Jurisdiction.US,
            origin=CandidateOrigin.CATALOG,
            text="El catálogo lo mapea a esta capacidad.",
            status=ExplanationStatus.WITHHELD,
        )


def test_a_candidate_is_never_left_without_text() -> None:
    with pytest.raises(ValidationError):
        CandidateExplanation(
            control_id="CTL-A",
            official_id="PR.AA-03",
            framework=Framework.CSF,
            jurisdiction=Jurisdiction.US,
            origin=CandidateOrigin.CATALOG,
            text="   ",
            status=ExplanationStatus.UNAVAILABLE,
        )


# --- the digest ---------------------------------------------------------------


def test_the_digest_names_exactly_what_was_shown() -> None:
    """UCM-16 records what the operator was reading; the digest is how it points."""
    shown = capability(["CTL-A"], [explanation("CTL-A")])
    same = capability(["CTL-A"], [explanation("CTL-A")])
    other = capability(["CTL-A"], [explanation("CTL-A", ExplanationStatus.UNAVAILABLE)])

    assert shown.digest == same.digest
    assert shown.digest != other.digest
