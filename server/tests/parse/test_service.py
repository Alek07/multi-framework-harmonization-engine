"""UCM-12 - The parse use case, against a scripted model.

Three things are asserted here that no amount of prompt work can guarantee on its
own: that a malformed answer is retried rather than accepted, that the run is
described well enough to be replayed, and that what comes back is a proposal —
gaps included — rather than a profile.
"""

from __future__ import annotations

import hashlib

import pytest

from app.parse.prompt import PROMPT_VERSION
from app.parse.service import AssetParseService, EmptyDescriptionError, ParseFailedError
from tests.parse.conftest import DESCRIPTION_ES, VERIFIED_DIGEST, draft_json, scripted_agent


async def parse(*replies: str, description: str = DESCRIPTION_ES, profile_id: str | None = None):
    with scripted_agent(*replies) as agent:
        return await AssetParseService(agent).parse(description, profile_id)


# --- the draft is a proposal, with its holes visible ---------------------------


async def test_parse_returns_a_draft_awaiting_review() -> None:
    result = await parse(draft_json())

    assert result.review_required is True
    assert result.draft.name == "Estación de ingeniería de gasoducto"
    assert result.profile_id == "ASSET-ESTACION-DE-INGENIERIA-DE-GASODUCTO"


async def test_the_silence_of_the_text_survives_the_parse() -> None:
    """What the description does not say comes back empty and listed as a gap."""
    result = await parse(draft_json())

    assert result.draft.zones[0].target_sl is None
    assert result.draft.nature.office_it_surface is None
    assert "zones[Z-ENG-STATION].target_sl" in result.missing_required
    assert "nature.office_it_surface" in result.missing_required


async def test_what_the_schema_cannot_hold_is_reported_not_dropped() -> None:
    """Invariant 2 at the parse boundary: no silent omission."""
    result = await parse(draft_json())

    assert result.draft.unmapped == ["El mantenimiento se hace los martes."]


async def test_every_extracted_value_carries_its_evidence() -> None:
    result = await parse(draft_json())

    note = result.draft.notes[0]
    assert note.field == "nature.general_purpose_os"
    assert note.evidence in DESCRIPTION_ES


async def test_caller_can_name_the_profile() -> None:
    result = await parse(draft_json(), profile_id="PROFILE-C")

    assert result.profile_id == "PROFILE-C"


# --- reproducibility ------------------------------------------------------------


async def test_provenance_describes_the_run_well_enough_to_replay_it() -> None:
    result = await parse(draft_json())

    provenance = result.provenance
    assert provenance.model_digest == VERIFIED_DIGEST
    assert provenance.prompt_version == PROMPT_VERSION
    assert provenance.temperature == 0.0
    assert provenance.seed == 42
    assert provenance.attempts == 1
    assert (
        provenance.source_sha256
        == hashlib.sha256(DESCRIPTION_ES.strip().encode("utf-8")).hexdigest()
    )


async def test_the_same_text_hashes_the_same_whatever_the_surrounding_whitespace() -> None:
    first = await parse(draft_json())
    second = await parse(draft_json(), description=f"\n  {DESCRIPTION_ES}  \n")

    assert first.provenance.source_sha256 == second.provenance.source_sha256


# --- retry on format failure ----------------------------------------------------


async def test_a_malformed_answer_is_retried_not_accepted() -> None:
    """The ticket's 'reintento en fallo de formato', asserted rather than assumed."""
    result = await parse('{"zones": "not a list"}', draft_json())

    assert result.draft.name == "Estación de ingeniería de gasoducto"
    assert result.provenance.attempts == 2


async def test_a_value_outside_the_schema_is_retried() -> None:
    """An SL of 7 is well-formed JSON and an invalid profile — it must not pass."""
    result = await parse(
        draft_json(zones=[{"id": "Z-A", "target_sl": 7}]),
        draft_json(zones=[{"id": "Z-A", "target_sl": 3}]),
    )

    assert result.draft.zones[0].target_sl == 3
    assert result.provenance.attempts == 2


async def test_a_model_that_never_gets_it_right_fails_loudly() -> None:
    with pytest.raises(ParseFailedError):
        await parse("no es json en absoluto")


# --- refusals -------------------------------------------------------------------


async def test_an_empty_description_never_reaches_the_model() -> None:
    with pytest.raises(EmptyDescriptionError):
        await parse(draft_json(), description="   \n  ")
