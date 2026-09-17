"""The explanations against the real model. Opt-in: `uv run pytest -m llm -s`.

Deselected by default, like the live parse test: it needs Ollama up with the pinned
model. What it checks cannot be scripted, because it is about the model itself and
the one risk here — a 7B asked to describe several candidates for the same capability
will, sooner or later, start comparing them.

* the model returns one explanation per candidate, in the offered order;
* the same candidates produce the same prose twice (temp 0 + fixed seed);
* whatever it writes, the candidate list is untouched and every candidate has
  text — generated, withheld or fallen back;
* how often the guard had to withhold is *printed*, not hidden behind a pass: the
  honest measure of how well the prompt holds, which belongs in the evaluation.

These tests run over the stand-in ranker's candidates, which is enough for the above
— the prose is the model's, whatever produced the list. The last test is marked
`rag` as well and runs the whole chain against Qdrant and e5-base
(`uv run pytest -m "llm and rag" -s`), because the similarity figures the model
repeats are only worth reading if they are the ones the shipped retriever would show.
"""

from __future__ import annotations

import sys

import pytest

from app.explain.schemas import CapabilityExplanations, ExplanationStatus
from app.explain.service import CandidateExplanationService
from tests.explain.conftest import Case

pytestmark = pytest.mark.llm

# A Windows console defaults to cp1252, which cannot encode the guillemets and
# accents the catalog is written in — the print would raise and take a ten-minute
# run's output with it. The whole point of this file is to *read* what the model
# wrote, so stdout is switched to UTF-8 instead of the prose being flattened.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")  # type: ignore[union-attr]


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
    # Without this the test passes on a total model failure: fail-open leaves the
    # candidates and their deterministic text in place, which is the contract but
    # is not what *this* file is here to check.
    assert result.generated, "the live model produced no usable explanation at all"


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


@pytest.mark.rag
async def test_the_whole_chain_over_the_real_index(
    service: CandidateExplanationService, live_case: Case
) -> None:
    """Catalog → core → Qdrant/e5 → 7B, with nothing stood in for.

    The point of running the real retriever here is the numbers: an explanation
    that quotes a similarity is only checkable if that similarity is the one the
    operator would see. It also exercises the case the stand-in ranker cannot
    produce — real neighbours, in the order real vectors put them.
    """
    result = await service.explain_capability(
        live_case.resolution, live_case.retrieval, live_case.catalog_version, live_case.zone
    )
    report(result)

    assert [e.control_id for e in result.explanations] == live_case.offered
    assert result.generated, "the live model produced no usable explanation at all"
    # Cosine similarities from e5-base, not a token-overlap stand-in.
    scores = [c.score for c in live_case.facts.candidates if c.score is not None]
    print(f"\nsimilitudes reales: {[round(score, 3) for score in scores]}")
    assert scores and all(0.0 <= score <= 1.0 for score in scores)
