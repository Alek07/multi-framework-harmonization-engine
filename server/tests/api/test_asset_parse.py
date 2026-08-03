"""UCM-15 - `POST /asset/parse`: a draft comes back, and nothing is decided.

The parse itself is covered in `tests/parse/`. What is asserted here is what the
*endpoint* adds: that the draft reaches the client intact, that an empty
description never reaches the model, that a model that cannot produce a valid
draft is a 502 rather than a half-parse — and that the whole call leaves the
append-only ledger untouched, because the LLM is not an actor (UCM-11).
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.repository import AuditRepository
from app.core.config import settings
from tests.api.conftest import PREFIX
from tests.parse.conftest import DESCRIPTION_ES, draft_json

URL = f"{PREFIX}/asset/parse"


def test_a_description_comes_back_as_a_reviewable_draft(
    client: TestClient, parsing: None
) -> None:
    response = client.post(URL, json={"description": DESCRIPTION_ES})

    assert response.status_code == 200
    body = response.json()
    assert body["review_required"] is True
    assert body["draft"]["name"] == "Estación de ingeniería de gasoducto"
    assert body["profile_id"] == "ASSET-ESTACION-DE-INGENIERIA-DE-GASODUCTO"


def test_what_the_text_does_not_say_comes_back_as_a_gap_not_a_guess(
    client: TestClient, parsing: None
) -> None:
    """The draft states no target SL and no criticality; neither may be invented."""
    body = client.post(URL, json={"description": DESCRIPTION_ES}).json()

    assert "zones[Z-ENG-STATION].target_sl" in body["missing_required"]
    assert "criticality.scale" in body["missing_required"]
    assert body["draft"]["zones"][0]["target_sl"] is None
    assert body["draft"]["criticality"]["scale"] is None


def test_nothing_the_text_said_is_dropped(client: TestClient, parsing: None) -> None:
    body = client.post(URL, json={"description": DESCRIPTION_ES}).json()
    assert body["draft"]["unmapped"] == ["El mantenimiento se hace los martes."]


def test_the_response_carries_what_is_needed_to_replay_it(
    client: TestClient, parsing: None
) -> None:
    provenance = client.post(URL, json={"description": DESCRIPTION_ES}).json()["provenance"]

    assert provenance["temperature"] == settings.LLM_TEMPERATURE == 0.0
    assert provenance["seed"] == settings.LLM_SEED
    assert provenance["model"] == settings.LLM_MODEL
    assert provenance["attempts"] == 1


def test_an_explicit_profile_id_is_used_verbatim(client: TestClient, parsing: None) -> None:
    body = client.post(URL, json={"description": DESCRIPTION_ES, "profile_id": "ASSET-X"}).json()
    assert body["profile_id"] == "ASSET-X"


def test_an_empty_description_never_reaches_the_model(client: TestClient) -> None:
    assert client.post(URL, json={"description": ""}).status_code == 422


def test_a_blank_description_is_refused_too(client: TestClient, parsing: None) -> None:
    response = client.post(URL, json={"description": "   "})
    assert response.status_code == 422
    assert "vacía" in response.json()["detail"]


def test_an_unknown_field_is_refused(client: TestClient, parsing: None) -> None:
    """`extra='forbid'`: a misspelled field is a bug, not a silently ignored option."""
    response = client.post(URL, json={"description": DESCRIPTION_ES, "profileId": "X"})
    assert response.status_code == 422


def test_a_model_that_cannot_produce_a_valid_draft_is_a_502(
    client: TestClient, scripted_parse: Callable[..., None]
) -> None:
    """Retries spent on an invalid answer: a failure, never a half-parse."""
    scripted_parse(draft_json(case="NOT_A_CASE"))

    response = client.post(URL, json={"description": DESCRIPTION_ES})
    assert response.status_code == 502
    assert "reintentos" in response.json()["detail"]


async def test_the_parse_writes_nothing_to_the_ledger(
    client: TestClient, parsing: None, db: AsyncSession
) -> None:
    """The LLM is not an actor: a proposal enters the log when a human confirms it."""
    assert client.post(URL, json={"description": DESCRIPTION_ES}).status_code == 200
    assert await AuditRepository(db).count() == 0
