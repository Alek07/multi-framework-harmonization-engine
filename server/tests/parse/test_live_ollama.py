"""The parse against the real model. Opt-in: `uv run pytest -m llm`.

Deselected by default because it needs Ollama up with the pinned model. What it
checks cannot be checked with a scripted model, because it is about the model itself:

* the 7B produces a draft the schema accepts, on the first request;
* two identical descriptions produce byte-identical drafts (temp 0 + fixed seed,
  invariant 3);
* it leaves unstated fields empty instead of filling them in, and puts what the
  schema cannot hold in `unmapped`.

The third can regress silently when the prompt is edited, which is why the prompt
carries a version.
"""

from __future__ import annotations

import pytest

from app.parse.service import AssetParseService
from tests.parse.conftest import DESCRIPTION_ES, DESCRIPTION_UNRATED_CONSEQUENCE

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


# --- The other direction: what the text *does* settle must come back ----------
#
# Every test above checks that the model stays quiet about what it was not told.
# None of them checked that it speaks about what it was. So a parse that returned
# almost nothing passed the whole suite — and one did: `zones`, `conduits` and
# `notes` came back absent, the schema allowed it, and Pydantic's defaults hid it.


async def test_a_described_zone_reaches_the_draft(service: AssetParseService) -> None:
    """The failure that started this. `DESCRIPTION_ES` describes one zone."""
    result = await service.parse(DESCRIPTION_ES)

    assert result.draft.zones, "the model answered with no zones at all"
    assert all(zone.id.startswith("Z-") for zone in result.draft.zones)


async def test_every_extracted_value_is_justified(service: AssetParseService) -> None:
    """`notes` is what the operator reviews; an empty list is an empty screen."""
    result = await service.parse(DESCRIPTION_ES)

    assert result.draft.notes, "the model extracted values without justifying any"
    assert all(note.evidence.strip() and note.note.strip() for note in result.draft.notes)


async def test_what_the_text_states_plainly_is_not_left_null(
    service: AssetParseService,
) -> None:
    """Windows and the connection to the PLCs are stated, not inferred from context."""
    result = await service.parse(DESCRIPTION_ES)

    assert result.draft.name
    assert result.draft.case is not None
    assert result.draft.zones, "the model answered with no zones at all"
    # One zone is described, and the premises belong to it: the Windows station is
    # the zone, not some asset-wide average of it.
    station = result.draft.zones[0]
    assert station.nature.general_purpose_os is True
    assert station.nature.networked is True


async def test_a_consequence_is_not_a_severity(service: AssetParseService) -> None:
    """A burst gas line sounds catastrophic. Saying so is the operator's call.

    `scale` is left null even when the text rates the consequence: it drives
    prioritisation, and rating it is judgement the parse must not make. See the
    note in `app/parse/prompt.py`.
    """
    result = await service.parse(DESCRIPTION_UNRATED_CONSEQUENCE)

    assert result.draft.criticality.physical_consequence, "the consequence itself is stated"
    assert result.draft.criticality.scale is None
    assert "criticality.scale" in result.missing_required
