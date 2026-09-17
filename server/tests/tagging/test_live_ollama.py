"""The tagger against the real model. Opt-in: `uv run pytest -m llm -s`.

Deselected by default, like the live parse and explain tests: it needs Ollama up
with the pinned model. What it checks cannot be scripted, because it is about the
model itself and the one risk here — a 7B asked "what does this control
presuppose?" will find a presupposition in almost anything, and a catalog where
every control presupposes a general-purpose OS discriminates as badly as one where
none does, while looking like progress.

So the assertions are deliberately few and the *printing* is the point:

* a governance control comes back with no premise (the over-tagging canary);
* a control that plainly needs an OS comes back naming it;
* the same control twice gives the same answer (temp 0 + fixed seed);
* the guard's rejection rate over a real sample is printed, not asserted — the
  honest measure of how well the prompt holds, which belongs in the evaluation.
"""

from __future__ import annotations

import sys

import pytest

from app.catalog.loader import get_catalog
from app.catalog.schemas import FrameworkControl
from app.tagging.schemas import ControlProposal, TagStatus
from app.tagging.service import ControlTaggingService

pytestmark = pytest.mark.llm

# A Windows console defaults to cp1252 and the catalog is written in Spanish.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")  # type: ignore[union-attr]

# A governance control (no technology presupposed) and a plainly OS-bound one.
GOVERNANCE = "CTL-CSF-GVOC01"
ANTIMALWARE = "CTL-CIS-1001"

# Enough controls to see the shape of the answers without a half-hour test.
SAMPLE = 12


@pytest.fixture
def service() -> ControlTaggingService:
    """The shipped agent, the real digest check, the real model."""
    return ControlTaggingService()


def control(control_id: str) -> FrameworkControl:
    return next(c for c in get_catalog().controls if c.id == control_id)


def report(proposal: ControlProposal) -> None:
    """Print what a reviewer would read. A silent LLM test proves very little."""
    print(f"\n=== {proposal.control_id} ({proposal.official_id}, {proposal.framework.value})")
    print(f"    {proposal.title}")
    print(f"    {proposal.paraphrased_description}")
    print(f"    estado: {proposal.status.value} · intentos: {proposal.attempts}")
    if proposal.notice:
        print(f"    aviso: {proposal.notice}")
    for premise in proposal.presupposes:
        print(f"    + {premise.premise.value} (expected={premise.expected}) — {premise.note}")
    for rejected in proposal.rejected:
        print(f"    - {rejected.premise} RECHAZADA: {rejected.reason}")
        print(f"      cita: «{rejected.quote}»")
    if not proposal.presupposes and not proposal.rejected:
        print("    (ninguna premisa — que es la respuesta esperada para la mayoría)")


async def test_a_governance_control_presupposes_nothing(
    service: ControlTaggingService,
) -> None:
    """The over-tagging canary. Keeping a register of who owns what needs no OS."""
    proposal = await service.tag(control(GOVERNANCE))
    report(proposal)

    assert proposal.status is TagStatus.NONE
    assert proposal.presupposes == []


async def test_a_control_that_needs_an_operating_system_says_so(
    service: ControlTaggingService,
) -> None:
    proposal = await service.tag(control(ANTIMALWARE))
    report(proposal)

    assert proposal.status is TagStatus.PROPOSED
    assert "general_purpose_os" in [p.premise.value for p in proposal.presupposes]


async def test_the_same_control_twice_gives_the_same_answer(
    service: ControlTaggingService,
) -> None:
    """Reproducibility (invariant 3) is what makes a one-off tagging run citable."""
    first = await service.tag(control(ANTIMALWARE))
    second = await service.tag(control(ANTIMALWARE))
    report(first)
    report(second)

    assert first.presupposes == second.presupposes


async def test_the_rejection_rate_over_a_real_sample_is_printed(
    service: ControlTaggingService,
) -> None:
    """Not asserted: this is the honest measure of how well the prompt holds."""
    sample = get_catalog().controls[:SAMPLE]
    proposals = [await service.tag(c) for c in sample]
    for proposal in proposals:
        report(proposal)

    tagged = [p for p in proposals if p.presupposes]
    rejected = sum(len(p.rejected) for p in proposals)
    proposed = sum(len(p.presupposes) for p in proposals) + rejected

    print(f"\n=== Muestra de {len(sample)} controles")
    print(f"    con alguna premisa tras el guard: {len(tagged)}")
    print(f"    premisas propuestas: {proposed} · rechazadas por el guard: {rejected}")
    print("    (una tasa de etiquetado cercana al 100 % es sobre-etiquetado, no cobertura)")

    assert len(proposals) == len(sample)
