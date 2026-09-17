"""The baseline endpoints: the trail, and the shape of a composition.

`GET /baseline/{id}/audit-log` is tested as the working endpoint it is. For
`POST /baseline/compose` only the request contract is tested here (what the
composition does lives in `test_compose.py`): the bodies quote a `run_id` the
ledger never saw, so anything past Pydantic is refused for that reason alone and
the two rejection causes stay distinguishable.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.repository import AuditRepository
from app.audit.schemas import (
    AuditActor,
    AuditEventCreate,
    AuditEventType,
    AuditStage,
)
from app.audit.service import AuditService
from tests.api.conftest import PREFIX

COMPOSE = f"{PREFIX}/baseline/compose"

RUN_ID = UUID("33333333-3333-3333-3333-333333333333")
BASELINE_ID = UUID("44444444-4444-4444-4444-444444444444")


def valid_composition(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "run_id": str(RUN_ID),
        "profile_id": "PROFILE-A",
        "choices": [
            {
                "kind": "option_selected",
                "zone_id": "Z-SIS",
                "capability_id": "CAP-PR-MFA",
                "control_id": "IEC-SR-1.1",
                "rationale": "Es el mecanismo del marco OT que gobierna la zona de seguridad.",
            }
        ],
        "signature": {
            "operator": "Responsable de ciberseguridad OT",
            "rationale": "Tier 0 completo y huecos aceptados por escrito.",
        },
    }
    body.update(overrides)
    return body


async def seed_trail(db: AsyncSession) -> AuditService:
    """One engine decision and one human decision, both under the same run.

    The engine's decisions are recorded before a baseline exists, so serving the
    trail by baseline has to walk back to the run; seeding both halves makes that
    observable.
    """
    audit = AuditService(AuditRepository(db))
    await audit.record(
        AuditEventCreate(
            actor=AuditActor.ENGINE,
            actor_ref="engine.mapping",
            stage=AuditStage.MAPPING,
            event_type=AuditEventType.CAPABILITY_MAPPED,
            run_id=RUN_ID,
            profile_id="PROFILE-A",
            zone_id="Z-SIS",
            capability_id="CAP-PR-MFA",
            decision="Se ofrecen 2 candidatos para la capacidad.",
            rationale="Mapeo determinista sobre el catálogo versionado.",
        )
    )
    await audit.record_human_decision(
        run_id=RUN_ID,
        profile_id="PROFILE-A",
        event_type=AuditEventType.BASELINE_SIGNED,
        decision="Se firma la línea base de PROFILE-A.",
        rationale="Tier 0 completo; huecos aceptados por escrito.",
        operator="Responsable de ciberseguridad OT",
        stage=AuditStage.SIGNATURE,
        baseline_id=BASELINE_ID,
    )
    return audit


# --- GET /baseline/{id}/audit-log ---------------------------------------------


async def test_the_trail_of_a_baseline_carries_both_actors(
    client: TestClient, db: AsyncSession
) -> None:
    await seed_trail(db)

    response = client.get(f"{PREFIX}/baseline/{BASELINE_ID}/audit-log")

    assert response.status_code == 200
    body = response.json()
    assert body["engine_events"] == 1
    assert body["human_events"] == 1
    assert [event["actor"] for event in body["events"]] == ["engine", "human"]


async def test_the_trail_reaches_back_to_the_run_the_baseline_was_composed_from(
    client: TestClient, db: AsyncSession
) -> None:
    """Serving only the signed events would be a trail that starts after the interesting part."""
    await seed_trail(db)

    events = client.get(f"{PREFIX}/baseline/{BASELINE_ID}/audit-log").json()["events"]

    assert events[0]["baseline_id"] is None
    assert events[0]["event_type"] == "capability_mapped"
    assert events[-1]["baseline_id"] == str(BASELINE_ID)


async def test_every_event_says_who_what_why_and_when(
    client: TestClient, db: AsyncSession
) -> None:
    await seed_trail(db)

    for event in client.get(f"{PREFIX}/baseline/{BASELINE_ID}/audit-log").json()["events"]:
        assert event["actor"] in {"engine", "human"}
        assert event["decision"].strip()
        assert event["rationale"].strip()
        assert event["recorded_at"]


async def test_the_trail_comes_with_proof_that_it_was_not_edited(
    client: TestClient, db: AsyncSession
) -> None:
    """Append-only is not only declared: the client gets the chain and can re-walk it."""
    await seed_trail(db)

    chain = client.get(f"{PREFIX}/baseline/{BASELINE_ID}/audit-log").json()["chain"]

    assert chain["valid"] is True
    assert chain["events"] == 2
    assert chain["first_broken_sequence"] is None


def test_a_baseline_with_no_trail_is_a_404(client: TestClient) -> None:
    response = client.get(f"{PREFIX}/baseline/{uuid4()}/audit-log")
    assert response.status_code == 404
    assert "append-only" in response.json()["detail"]


def test_a_malformed_baseline_id_is_a_422(client: TestClient) -> None:
    assert client.get(f"{PREFIX}/baseline/not-a-uuid/audit-log").status_code == 422


# --- POST /baseline/compose: the request contract ----------------------------
# Only the shape of the request is checked here; a `run_id` the ledger never saw
# means anything past Pydantic is refused for that reason (422), never a field.


def test_a_well_formed_composition_reaches_the_engine(client: TestClient) -> None:
    """Well formed is not the same as admissible: this run does not exist."""
    response = client.post(COMPOSE, json=valid_composition())

    assert response.status_code == 422
    assert "no tiene ninguna ejecución" in response.json()["detail"]


def test_a_choice_without_a_written_justification_is_refused(client: TestClient) -> None:
    """The ledger's own rule, enforced at the boundary: no rationale, no decision."""
    body = valid_composition()
    body["choices"][0]["rationale"] = "   "

    assert client.post(COMPOSE, json=body).status_code == 422


def test_a_selection_must_name_the_control_it_selects(client: TestClient) -> None:
    body = valid_composition()
    body["choices"][0].pop("control_id")

    response = client.post(COMPOSE, json=body)
    assert response.status_code == 422
    assert "control" in response.text


def test_accepting_a_gap_may_not_name_a_control(client: TestClient) -> None:
    """A gap is the absence of a mechanism: accepting one while naming it is incoherent."""
    body = valid_composition()
    body["choices"][0] = {
        "kind": "gap_accepted",
        "zone_id": "Z-SIS",
        "capability_id": "CAP-PR-MFA",
        "control_id": "IEC-SR-1.1",
        "rationale": "Se acepta el hueco con control compensatorio organizativo.",
    }

    assert client.post(COMPOSE, json=body).status_code == 422


def test_accepting_a_gap_without_a_control_is_well_formed(client: TestClient) -> None:
    body = valid_composition()
    body["choices"][0] = {
        "kind": "gap_accepted",
        "zone_id": "Z-SIS",
        "capability_id": "CAP-PR-MFA",
        "rationale": "Se acepta el hueco y se documenta en la capa organizativa.",
    }

    response = client.post(COMPOSE, json=body)
    assert response.status_code == 422
    assert "no tiene ninguna ejecución" in response.json()["detail"]


def test_a_composition_with_no_choices_is_refused(client: TestClient) -> None:
    assert client.post(COMPOSE, json=valid_composition(choices=[])).status_code == 422


def test_an_unsigned_composition_is_refused(client: TestClient) -> None:
    body = valid_composition()
    body.pop("signature")

    assert client.post(COMPOSE, json=body).status_code == 422


def test_a_signature_without_a_named_operator_is_refused(client: TestClient) -> None:
    """Nothing anonymous reaches the ledger: the signature has an actor or it is not one."""
    body = valid_composition()
    body["signature"]["operator"] = ""

    assert client.post(COMPOSE, json=body).status_code == 422


def test_a_composition_that_names_no_engine_run_is_refused(client: TestClient) -> None:
    """The human's decisions chain onto a run: without one there is nothing to chain to."""
    body = valid_composition()
    body.pop("run_id")

    assert client.post(COMPOSE, json=body).status_code == 422


def test_an_unknown_kind_of_choice_is_refused(client: TestClient) -> None:
    body = valid_composition()
    body["choices"][0]["kind"] = "option_ignored"

    assert client.post(COMPOSE, json=body).status_code == 422
