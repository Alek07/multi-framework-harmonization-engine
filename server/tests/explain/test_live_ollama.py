"""UCM-14 - The explanations against the real model. Opt-in: `uv run pytest -m llm -s`.

Deselected by default, like the live parse test (UCM-12): it needs Ollama up with
the pinned model. What it checks cannot be scripted, because it is about the model
itself and about the one risk this ticket carries — a 7B asked to describe several
candidates for the same capability will, sooner or later, start comparing them.

* the model returns one explanation per candidate, in the offered order;
* the same candidates produce the same prose twice (temp 0 + fixed seed);
* whatever it writes, the candidate list is untouched and every candidate has
  text — generated, withheld or fallen back;
* how often the guard had to withhold is *printed*, not hidden behind a pass:
  that number is the honest measure of how well the prompt holds, and it belongs
  in the evaluation (UCM-18), not in a green tick.
"""

from __future__ import annotations

import pytest

from app.explain.schemas import CapabilityExplanations, ExplanationStatus
from app.explain.service import CandidateExplanationService
from tests.explain.conftest import Case

pytestmark = pytest.mark.llm


@pytest.fixture
def service() -> CandidateExplanationService:
    """The shipped agent, the real digest check, the real model."""
    return CandidateExplanationService()


def report(result: CapabilityExplanations) -> None:
    """Print what the operator would read. A silent LLM test proves very little."""
    print(f"\n=== {result.capability_id} — {result.capability_name} ({result.zone_id}) ===")
    print(f"    modelo: {result.provenance.model} · intentos: {result.provenance.attempts}")
    if result.provenance.notice:
        print(f"    aviso: {result.provenance.notice}")
    if result.provenance.ignored_control_ids:
        print(f"    ignorados: {result.provenance.ignored_control_ids}")
    for position, explanation in enumerate(result.explanations, start=1):
        basis = ", ".join(key.value for key in explanation.basis) or "—"
        print(
            f"\n  {position}. [{explanation.origin.value}] {explanation.control_id} "
            f"({explanation.official_id}, {explanation.framework.value}) "
            f"→ {explanation.status.value}"
        )
        print(f"     {explanation.text}")
        print(f"     basis: {basis}")
        if explanation.notice:
            print(f"     nota: {explanation.notice}")


async def test_the_model_explains_every_candidate_and_only_them(
    service: CandidateExplanationService, case: Case
) -> None:
    result = await service.explain_capability(
        case.resolution, case.retrieval, case.catalog_version, case.zone
    )
    report(result)

    assert [e.control_id for e in result.explanations] == case.offered
    assert all(e.text.strip() for e in result.explanations)
    assert result.provenance.model_digest


async def test_the_explanations_are_reproducible(
    service: CandidateExplanationService, case: Case
) -> None:
    first = await service.explain_capability(
        case.resolution, case.retrieval, case.catalog_version, case.zone
    )
    second = await service.explain_capability(
        case.resolution, case.retrieval, case.catalog_version, case.zone
    )

    print(f"\ndigest 1: {first.digest}\ndigest 2: {second.digest}")
    assert first.digest == second.digest
    assert [e.text for e in first.explanations] == [e.text for e in second.explanations]


async def test_what_the_guard_had_to_withhold_is_reported(
    service: CandidateExplanationService, case: Case
) -> None:
    """Not an assertion about the model's obedience — a measurement of it."""
    result = await service.explain_capability(
        case.resolution, case.retrieval, case.catalog_version, case.zone
    )

    generated = len(result.generated)
    withheld = len(result.withheld)
    missing = sum(1 for e in result.explanations if e.status is ExplanationStatus.UNAVAILABLE)
    print(
        f"\ncandidatos: {len(result.explanations)} · generadas: {generated} · "
        f"retenidas: {withheld} · sin explicación: {missing}"
    )
    for explanation in result.withheld:
        print(f"  retenida {explanation.control_id}: {explanation.notice}")

    # The candidate list is what must survive the model, not the prose.
    assert result.offered_control_ids == case.offered
