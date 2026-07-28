"""UCM-12 - The parse against the real model. Opt-in: `uv run pytest -m llm`.

Deselected by default because it needs Ollama up with the pinned model — the rest
of the suite must stay runnable on any machine. What it checks cannot be checked
with a scripted model, because it is about the model itself:

* the 7B produces a draft the schema accepts, on the first request;
* two identical descriptions produce byte-identical drafts (temp 0 + fixed seed,
  invariant 3 — the claim the whole POC rests on);
* it leaves unstated fields empty instead of filling them in, and puts what the
  schema cannot hold in `unmapped`.

The third is the one that can regress silently when the prompt is edited, and it
is the reason the prompt carries a version.
"""

from __future__ import annotations

import pytest

from app.parse.service import AssetParseService
from tests.parse.conftest import DESCRIPTION_ES

pytestmark = pytest.mark.llm


@pytest.fixture
def service() -> AssetParseService:
    """The shipped agent, the real digest check, the real model."""
    return AssetParseService()


async def test_the_model_returns_a_valid_draft(service: AssetParseService) -> None:
    result = await service.parse(DESCRIPTION_ES)

    assert result.draft.name
    assert result.draft.zones
    assert result.review_required is True
    # A retry would still be a pass; a first-attempt parse is what we expect of
    # this prompt, and a regression to 2 is worth seeing in the report.
    assert result.provenance.attempts == 1


async def test_the_parse_is_reproducible(service: AssetParseService) -> None:
    first = await service.parse(DESCRIPTION_ES)
    second = await service.parse(DESCRIPTION_ES)

    assert first.draft.model_dump_json() == second.draft.model_dump_json()


async def test_the_model_does_not_invent_what_the_text_omits(
    service: AssetParseService,
) -> None:
    """The description gives no target SL and no physical consequence."""
    result = await service.parse(DESCRIPTION_ES)

    assert all(zone.target_sl is None for zone in result.draft.zones)
    assert result.draft.criticality.scale is None
    assert result.missing_required


async def test_what_does_not_fit_the_schema_is_reported(service: AssetParseService) -> None:
    result = await service.parse(DESCRIPTION_ES)

    assert any("martes" in item.lower() for item in result.draft.unmapped)
