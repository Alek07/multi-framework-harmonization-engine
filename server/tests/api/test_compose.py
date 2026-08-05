"""UCM-16 - Sovereign composition: the human chooses, the engine verifies, both sign.

These are the assertions the central contribution of the TFM stands on, so they
are written about the claims rather than about the code:

* **Tier 0 complete is verified before the signature, never after.** A composition
  that leaves one mandate open is refused, and the refusal names it.
* **Nothing mandatory ends up in a signed baseline anonymously.** Every Tier 0
  capability of every zone leaves a human-authored entry — chosen, compensated,
  accepted as a gap or ratified — and ratifying is a different event type from
  choosing, so the log can never claim a selection nobody made.
* **The signature is anchored.** It hangs from the engine run the options came
  from, it refuses a run that was computed under other versions, and a run is
  signed once.
* **It works with no AI at all.** Everything below runs with no Ollama and no
  Qdrant: the composition re-runs the deterministic core, so what a human can sign
  never depends on a model being up.
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
from app.candidates.service import CandidatesService
from tests.api.conftest import PREFIX

COMPOSE = f"{PREFIX}/baseline/compose"

SIGNATURE = {
    "operator": "Responsable de ciberseguridad OT",
    "rationale": (
        "Bloque obligatorio completo por zona; los mandatos que el motor no cerró se asumen "
        "por escrito y con control compensatorio organizativo donde procede."
    ),
}


def closing_choices(run: dict[str, Any], reason: str = "Se acepta el residual.") -> list[dict]:
    """Close every outstanding mandate of every zone by accepting the gap in writing."""
    return [
        {
            "kind": "gap_accepted",
            "zone_id": zone["zone"]["zone_id"],
            "capability_id": capability_id,
            "rationale": f"{reason} ({zone['zone']['zone_id']}/{capability_id})",
        }
        for zone in run["zones"]
        for capability_id in zone["outstanding_capability_ids"]
    ]


def composition(run: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "run_id": run["run_id"],
        "profile_id": "PROFILE-A",
        "choices": closing_choices(run),
        "signature": SIGNATURE,
    }
    body.update(overrides)
    return body


def sign(client: TestClient, run: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    response = client.post(COMPOSE, json=composition(run, **overrides))
    assert response.status_code == 201, response.text
    return dict(response.json())


def offered(run: dict[str, Any], zone_id: str, capability_id: str) -> list[str]:
    zone = next(z for z in run["zones"] if z["zone"]["zone_id"] == zone_id)
    return list(
        next(c for c in zone["capabilities"] if c["capability_id"] == capability_id)[
            "offered_control_ids"
        ]
    )


# --- the happy path -----------------------------------------------------------


def test_a_composition_that_closes_every_mandate_is_signed(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    baseline = sign(client, engine_run)

    assert baseline["run_id"] == engine_run["run_id"]
    assert baseline["profile_id"] == "PROFILE-A"
    assert baseline["signed_by"] == SIGNATURE["operator"]
    assert baseline["tier_0_complete"] is True
    assert UUID(baseline["baseline_id"])


def test_the_signed_baseline_points_at_its_own_trail(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    """A signature whose evidence cannot be found is a signature over nothing."""
    baseline = sign(client, engine_run)

    assert baseline["audit_log_path"] == f"{PREFIX}/baseline/{baseline['baseline_id']}/audit-log"
    trail = client.get(baseline["audit_log_path"])
    assert trail.status_code == 200
    assert trail.json()["chain"]["valid"] is True


def test_the_versions_that_governed_the_run_are_part_of_the_signature(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    """The same signature over another catalog would be another baseline (invariant 3)."""
    baseline = sign(client, engine_run)

    assert baseline["versions"] == {
        "catalog": engine_run["catalog_version"],
        "rules": engine_run["rules_version"],
        "gating": engine_run["gating_version"],
        "prioritization": engine_run["prioritization_version"],
    }


def test_signing_needs_no_ai_at_all(
    client: TestClient, candidates_without_index: CandidatesService
) -> None:
    """Qdrant down, Ollama down: the operator can still compose and sign."""
    run = client.post(f"{PREFIX}/candidates", json={"profile_id": "PROFILE-A"}).json()
    assert run["retrieval"]["status"] == "unavailable"

    response = client.post(COMPOSE, json=composition(run))
    assert response.status_code == 201, response.text


# --- Tier 0 complete, verified before the signature ---------------------------


def test_every_mandatory_capability_is_in_the_baseline(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    baseline = sign(client, engine_run)

    for zone in baseline["zones"]:
        tier_0 = [c for c in zone["capabilities"] if c["tier"] == "tier_0"]
        assert len(tier_0) == 30
        assert zone["tier_0_complete"] is True
        assert all(c["required"] is True for c in tier_0)


def test_no_mandatory_capability_is_left_anonymous(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    """Chosen, compensated, accepted as a gap, or ratified — but never nothing."""
    baseline = sign(client, engine_run)

    for zone in baseline["zones"]:
        for capability in zone["capabilities"]:
            if capability["tier"] != "tier_0":
                continue
            decided = (
                capability["selected_control_ids"]
                or capability["compensatory_control_ids"]
                or capability["gap_accepted"]
            )
            ratified = capability["ratified_control_ids"] or capability["status"] in {
                "deferred_to_organizational_layer",
                "compensatory_required",
            }
            assert decided or ratified, capability["capability_id"]


def test_an_open_mandate_refuses_the_signature_and_names_it(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    choices = closing_choices(engine_run)
    dropped = choices.pop()

    response = client.post(COMPOSE, json=composition(engine_run, choices=choices))

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert "bloque obligatorio está incompleto" in detail
    assert f"{dropped['zone_id']}/{dropped['capability_id']}" in detail


def test_rejecting_a_candidate_does_not_close_a_mandate(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    """Discarding an option is part of the record; it puts no mechanism in the baseline."""
    choices = closing_choices(engine_run)
    open_one = choices.pop()
    zone_id, capability_id = open_one["zone_id"], open_one["capability_id"]
    choices.append(
        {
            "kind": "option_rejected",
            "zone_id": zone_id,
            "capability_id": capability_id,
            "control_id": offered(engine_run, zone_id, capability_id)[0],
            "rationale": "No aplica al corredor OT por su premisa técnica.",
        }
    )

    response = client.post(COMPOSE, json=composition(engine_run, choices=choices))
    assert response.status_code == 409
    assert f"{zone_id}/{capability_id}" in response.json()["detail"]


def test_a_mandate_can_be_closed_by_choosing_a_mechanism(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    choices = closing_choices(engine_run)
    replaced = choices.pop(0)
    zone_id, capability_id = replaced["zone_id"], replaced["capability_id"]
    control_id = offered(engine_run, zone_id, capability_id)[0]
    choices.insert(
        0,
        {
            "kind": "option_selected",
            "zone_id": zone_id,
            "capability_id": capability_id,
            "control_id": control_id,
            "rationale": "Es el mecanismo del marco OT que gobierna esta zona.",
        },
    )

    baseline = sign(client, engine_run, choices=choices)
    capability = next(
        c
        for z in baseline["zones"]
        if z["zone_id"] == zone_id
        for c in z["capabilities"]
        if c["capability_id"] == capability_id
    )
    assert capability["selected_control_ids"] == [control_id]
    assert capability["gap_accepted"] is False
    assert capability["ratified_control_ids"] == []


def test_a_mandate_can_be_closed_by_a_compensatory_control(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    choices = closing_choices(engine_run)
    replaced = choices.pop(0)
    zone_id, capability_id = replaced["zone_id"], replaced["capability_id"]
    control_id = offered(engine_run, zone_id, capability_id)[0]
    choices.insert(
        0,
        {
            "kind": "compensatory_declared",
            "zone_id": zone_id,
            "capability_id": capability_id,
            "control_id": control_id,
            "rationale": "El activo no admite el mecanismo; se compensa en el conducto.",
        },
    )

    baseline = sign(client, engine_run, choices=choices)
    capability = next(
        c
        for z in baseline["zones"]
        if z["zone_id"] == zone_id
        for c in z["capabilities"]
        if c["capability_id"] == capability_id
    )
    assert capability["compensatory_control_ids"] == [control_id]


# --- ratification is not selection --------------------------------------------


def test_untouched_mandates_are_ratified_not_selected(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    baseline = sign(client, engine_run)

    for zone in baseline["zones"]:
        ratified = [
            c
            for c in zone["capabilities"]
            if c["tier"] == "tier_0" and not c["gap_accepted"] and c["ratified_control_ids"]
        ]
        assert ratified
        for capability in ratified:
            assert capability["selected_control_ids"] == []
            assert "ratificado" in capability["rationale"]


async def test_the_ledger_tells_a_ratification_from_a_choice(
    client: TestClient, engine_run: dict[str, Any], db: AsyncSession
) -> None:
    """The whole point of the separate event type: two different sentences."""
    baseline = sign(client, engine_run)
    events = await AuditRepository(db).by_run(UUID(engine_run["run_id"]))
    human = [e for e in events if e.actor is AuditActor.HUMAN]

    ratified = [e for e in human if e.event_type is AuditEventType.MECHANISM_RATIFIED]
    accepted = [e for e in human if e.event_type is AuditEventType.GAP_ACCEPTED]
    signed = [e for e in human if e.event_type is AuditEventType.BASELINE_SIGNED]

    # 11 open mandates across the two zones of PROFILE-A (5 in the corridor, 6 in
    # the crown jewel, which admits less) and 49 mandates the core already closed
    # and the signature ratifies without asking the operator to re-justify them.
    assert len(accepted) == 11
    assert len(ratified) == 49
    assert len(signed) == 1
    assert baseline["audit_events"] == len(human) == 61
    assert all(e.baseline_id == UUID(baseline["baseline_id"]) for e in human)
    assert all("Ratificación, no selección" in e.rationale for e in ratified)


async def test_every_human_entry_carries_a_written_reason_and_an_actor(
    client: TestClient, engine_run: dict[str, Any], db: AsyncSession
) -> None:
    sign(client, engine_run)
    events = await AuditRepository(db).by_run(UUID(engine_run["run_id"]))

    for event in (e for e in events if e.actor is AuditActor.HUMAN):
        assert event.actor_ref == SIGNATURE["operator"]
        assert event.decision.strip()
        assert event.rationale.strip()
        assert event.versions


async def test_the_composition_extends_the_same_chain(
    client: TestClient, engine_run: dict[str, Any], db: AsyncSession
) -> None:
    sign(client, engine_run)
    verification = await AuditService(AuditRepository(db)).verify_run(
        UUID(engine_run["run_id"])
    )
    assert verification.valid, verification.detail


# --- adopting a suggestion is recorded as an adoption -------------------------


def test_adopting_a_control_the_catalog_does_not_map_is_marked_as_such(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    """An embedding distance does not become an authored mapping because a human agreed."""
    zone = engine_run["zones"][0]
    # Not one of the outstanding mandates: those are already closed by an accepted
    # gap below, and a capability cannot both accept its gap and adopt a mechanism.
    capability = next(
        c
        for c in zone["capabilities"]
        if c["capability_id"] not in zone["outstanding_capability_ids"]
        and c["retrieval"]
        and c["retrieval"]["retrieved"]
        and len(c["offered_control_ids"]) > 1
    )
    mapped = [o["control"]["id"] for o in capability["resolution"]["options"]]
    suggestion = next(c for c in capability["offered_control_ids"] if c not in mapped)

    choices = closing_choices(engine_run)
    choices.append(
        {
            "kind": "option_selected",
            "zone_id": zone["zone"]["zone_id"],
            "capability_id": capability["capability_id"],
            "control_id": suggestion,
            "rationale": "Se adopta la sugerencia: cubre el objetivo en esta zona.",
        }
    )

    baseline = sign(client, engine_run, choices=choices)
    composed = next(
        c
        for z in baseline["zones"]
        if z["zone_id"] == zone["zone"]["zone_id"]
        for c in z["capabilities"]
        if c["capability_id"] == capability["capability_id"]
    )
    assert suggestion in composed["adopted_control_ids"]
    assert "adopción de sugerencia" in composed["rationale"]


# --- the signature is anchored ------------------------------------------------


def test_a_run_the_ledger_never_saw_is_refused(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    response = client.post(COMPOSE, json=composition(engine_run, run_id=str(uuid4())))
    assert response.status_code == 422
    assert "no tiene ninguna ejecución" in response.json()["detail"]


def test_signing_one_profile_with_another_profiles_run_is_refused(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    response = client.post(COMPOSE, json=composition(engine_run, profile_id="PROFILE-B"))
    assert response.status_code == 422
    assert "PROFILE-A" in response.json()["detail"]


def test_a_run_is_signed_only_once(client: TestClient, engine_run: dict[str, Any]) -> None:
    """Two baselines over the same evidence would leave nobody knowing which is in force."""
    first = sign(client, engine_run)

    response = client.post(COMPOSE, json=composition(engine_run))
    assert response.status_code == 409
    assert first["baseline_id"] in response.json()["detail"]


async def test_a_run_computed_under_other_versions_is_refused(
    client: TestClient, offline_candidates: CandidatesService, db: AsyncSession
) -> None:
    """Signing against a moved catalog would attest to options nobody ever saw."""
    stale_run = uuid4()
    await AuditService(AuditRepository(db)).record(
        AuditEventCreate(
            actor=AuditActor.ENGINE,
            actor_ref="engine.service",
            stage=AuditStage.RUN,
            event_type=AuditEventType.RUN_STARTED,
            run_id=stale_run,
            profile_id="PROFILE-A",
            decision="Ejecución del núcleo determinista sobre el perfil PROFILE-A",
            rationale="Ejecución antigua, calculada con un catálogo anterior.",
            versions={"catalog": "0.0.1", "rules": "0.0.1"},
        )
    )

    response = client.post(
        COMPOSE,
        json={
            "run_id": str(stale_run),
            "profile_id": "PROFILE-A",
            "choices": [
                {
                    "kind": "gap_accepted",
                    "zone_id": "Z-SIS",
                    "capability_id": "CAP-PR-MFA",
                    "rationale": "Se acepta el residual.",
                }
            ],
            "signature": SIGNATURE,
        },
    )
    assert response.status_code == 409
    assert "cambiaron desde la ejecución" in response.json()["detail"]
    assert "catalog: la ejecución usó 0.0.1" in response.json()["detail"]


# --- what the engine refuses to record ----------------------------------------


def test_a_control_outside_the_catalog_is_refused(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    choices = closing_choices(engine_run)
    choices[0] = {
        "kind": "option_selected",
        "zone_id": choices[0]["zone_id"],
        "capability_id": choices[0]["capability_id"],
        "control_id": "NO-EXISTE-1",
        "rationale": "Un mecanismo inventado.",
    }

    response = client.post(COMPOSE, json=composition(engine_run, choices=choices))
    assert response.status_code == 422
    assert "NO-EXISTE-1" in response.json()["detail"]


def test_an_unknown_zone_is_refused(client: TestClient, engine_run: dict[str, Any]) -> None:
    choices = closing_choices(engine_run)
    choices[0]["zone_id"] = "Z-NOPE"

    response = client.post(COMPOSE, json=composition(engine_run, choices=choices))
    assert response.status_code == 422
    assert "Z-NOPE" in response.json()["detail"]


def test_an_unknown_capability_is_refused(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    choices = closing_choices(engine_run)
    choices[0]["capability_id"] = "CAP-NOPE"

    response = client.post(COMPOSE, json=composition(engine_run, choices=choices))
    assert response.status_code == 422
    assert "CAP-NOPE" in response.json()["detail"]


def test_a_repeated_decision_is_refused(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    choices = closing_choices(engine_run)
    choices.append(dict(choices[0]))

    response = client.post(COMPOSE, json=composition(engine_run, choices=choices))
    assert response.status_code == 422
    assert "repetida" in response.json()["detail"]


def test_choosing_and_discarding_the_same_control_is_refused(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    choices = closing_choices(engine_run)
    zone_id, capability_id = choices[0]["zone_id"], choices[0]["capability_id"]
    control_id = offered(engine_run, zone_id, capability_id)[0]
    choices[0] = {
        "kind": "option_selected",
        "zone_id": zone_id,
        "capability_id": capability_id,
        "control_id": control_id,
        "rationale": "Se elige este mecanismo.",
    }
    choices.append(
        {
            "kind": "option_rejected",
            "zone_id": zone_id,
            "capability_id": capability_id,
            "control_id": control_id,
            "rationale": "Y a la vez se descarta.",
        }
    )

    response = client.post(COMPOSE, json=composition(engine_run, choices=choices))
    assert response.status_code == 422
    assert control_id in response.json()["detail"]


def test_accepting_a_gap_while_adopting_a_mechanism_is_refused(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    choices = closing_choices(engine_run)
    zone_id, capability_id = choices[0]["zone_id"], choices[0]["capability_id"]
    choices.append(
        {
            "kind": "option_selected",
            "zone_id": zone_id,
            "capability_id": capability_id,
            "control_id": offered(engine_run, zone_id, capability_id)[0],
            "rationale": "Se elige un mecanismo para la misma capacidad.",
        }
    )

    response = client.post(COMPOSE, json=composition(engine_run, choices=choices))
    assert response.status_code == 422
    assert "acepta el hueco" in response.json()["detail"]


# --- what the baseline contains -----------------------------------------------


def test_untouched_discretionary_capabilities_are_not_in_the_baseline(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    """Tier 1 nobody decided about is not part of what was signed."""
    baseline = sign(client, engine_run)

    for zone in baseline["zones"]:
        assert all(c["tier"] == "tier_0" for c in zone["capabilities"])


def test_a_discretionary_choice_enters_the_baseline(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    zone = engine_run["zones"][0]
    zone_id = zone["zone"]["zone_id"]
    tier_1 = next(c for c in zone["capabilities"] if c["priority"]["tier"] == "tier_1")
    control_id = tier_1["offered_control_ids"][0]

    choices = closing_choices(engine_run)
    choices.append(
        {
            "kind": "option_selected",
            "zone_id": zone_id,
            "capability_id": tier_1["capability_id"],
            "control_id": control_id,
            "rationale": "Se adelanta esta capacidad discrecional por su apalancamiento.",
        }
    )

    baseline = sign(client, engine_run, choices=choices)
    composed = next(z for z in baseline["zones"] if z["zone_id"] == zone_id).__getitem__(
        "capabilities"
    )
    discretionary = [c for c in composed if c["tier"] == "tier_1"]
    assert [c["capability_id"] for c in discretionary] == [tier_1["capability_id"]]
    assert discretionary[0]["selected_control_ids"] == [control_id]


def test_the_baseline_names_the_mandates_the_human_had_to_close(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    baseline = sign(client, engine_run)

    for zone, signed_zone in zip(engine_run["zones"], baseline["zones"], strict=True):
        assert signed_zone["outstanding_capability_ids"] == zone["outstanding_capability_ids"]
        assert "bloque obligatorio completo" in signed_zone["rationale"]
