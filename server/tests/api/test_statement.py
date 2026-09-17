"""The baseline as a declaration of applicability, and as a partial OSCAL SSP.

Written about the claims the artefact supports:

* **Nothing is missing from the document.** Every required capability of every
  zone has a row — the same set the ledger's own mapping stage accounted for. The
  0-silent-omissions invariant is measurable on the *document*, not only on the
  engine and on the trail.
* **Every inclusion and every exclusion carries a written reason.** That is the
  discipline an SoA exists for, and here it is enforced by the ledger the document
  is projected from: an entry without a justification cannot be appended.
* **Ratifying is not choosing, in the document too.** The distinction the trail
  makes with two event types survives into the artefact a third party reads.
* **It is a projection.** Asking for the document changes nothing and adds
  nothing to the ledger, and asking twice gives the same bytes.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from tests.api.conftest import PREFIX
from tests.api.test_compose import SIGNATURE, closing_choices, offered, sign


def statement(client: TestClient, baseline_id: str, **params: str) -> dict[str, Any]:
    response = client.get(f"{PREFIX}/baseline/{baseline_id}/statement", params=params)
    assert response.status_code == 200, response.text
    return dict(response.json())


def rows(document: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for zone in document["zones"] for row in zone["rows"]]


def mechanisms(document: dict[str, Any]) -> list[dict[str, Any]]:
    return [mechanism for row in rows(document) for mechanism in row["mechanisms"]]


def accounted_for(client: TestClient, baseline_id: str) -> dict[str, set[str]]:
    """Per zone, the capabilities the ledger's mapping stage says it accounted for.

    Read from `stage_completed`, which is the engine's own statement of what it
    walked — so the document is checked against the trail rather than against the
    catalog, and a capability lost between the two would show up here.
    """
    trail = client.get(f"{PREFIX}/baseline/{baseline_id}/audit-log").json()
    return {
        event["zone_id"]: set(event["payload"]["capability_ids"])
        for event in trail["events"]
        if event["event_type"] == "stage_completed" and event["stage"] == "mapping"
    }


# --- nothing missing ----------------------------------------------------------


def test_every_required_capability_of_every_zone_has_a_row(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    """0 silent omissions, measured on the document a third party reads."""
    baseline = sign(client, engine_run)
    document = statement(client, baseline["baseline_id"])
    expected = accounted_for(client, baseline["baseline_id"])

    assert expected, "the trail should account for at least one zone"
    assert {zone["zone_id"] for zone in document["zones"]} == set(expected)
    for zone in document["zones"]:
        assert {row["capability_id"] for row in zone["rows"]} == expected[zone["zone_id"]]


def test_no_row_can_say_that_a_required_capability_does_not_apply(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    """Gating removes mechanisms, never requirements — including in the document."""
    baseline = sign(client, engine_run)
    document = statement(client, baseline["baseline_id"])

    assert all(row["required"] is True for row in rows(document))
    assert {row["outcome"] for row in rows(document)} <= {
        "implemented",
        "compensated",
        "deferred",
        "accepted_gap",
        "open_gap",
        "roadmap",
    }


def test_a_capability_the_operator_never_decided_is_not_passed_off_as_signed(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    """Tier 1 nobody touched is a recommendation, and the document says which it is."""
    baseline = sign(client, engine_run)
    document = statement(client, baseline["baseline_id"])

    roadmap = [row for row in rows(document) if row["outcome"] == "roadmap"]
    assert roadmap, "profile A should leave discretionary capabilities undecided"
    assert all(row["in_signed_baseline"] is False for row in roadmap)
    assert all(row["tier"] == "tier_1" for row in roadmap)
    assert all(row["in_signed_baseline"] for row in rows(document) if row["tier"] == "tier_0")


# --- every decision with its reason -------------------------------------------


def test_every_row_carries_a_justification(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    baseline = sign(client, engine_run)
    document = statement(client, baseline["baseline_id"])

    for row in rows(document):
        assert row["engine_rationale"].strip(), row["capability_id"]
        if row["decided_by_human"]:
            assert (row["human_rationale"] or "").strip(), row["capability_id"]


def test_the_operators_own_words_are_what_the_document_quotes(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    """A rendering of the reason is not the reason: the ledger's text travels verbatim."""
    reason = "Sin mecanismo aplicable en la zona; el residual se asume con vigilancia reforzada."
    baseline = sign(client, engine_run, choices=closing_choices(engine_run, reason))
    document = statement(client, baseline["baseline_id"])

    decided = [row for row in rows(document) if row["decided_by_human"]]
    assert decided, "the fixture composition closes at least one mandate by hand"
    assert all(reason in row["human_rationale"] for row in decided)
    assert SIGNATURE["rationale"] in document["signature_rationale"]


def test_a_justified_exclusion_names_its_rule_and_the_premise_that_fired_it(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    """An exclusion without evidence is an opinion; this is the SoA's own deliverable."""
    baseline = sign(client, engine_run)
    document = statement(client, baseline["baseline_id"])

    excluded = [
        mechanism
        for mechanism in mechanisms(document)
        if mechanism["disposition"]
        in {"not_applicable", "objective_without_mechanism", "wrong_scope"}
    ]
    assert excluded, "profile A should have gating exclusions to declare"
    for mechanism in excluded:
        assert mechanism["rule_id"], mechanism["control_id"]
        assert mechanism["evidence"], mechanism["control_id"]
        assert mechanism["rationale"].strip()
        assert mechanism["included"] is False


def test_an_accepted_gap_travels_with_its_written_acceptance(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    baseline = sign(client, engine_run)
    document = statement(client, baseline["baseline_id"])

    accepted = [row for row in rows(document) if row["outcome"] == "accepted_gap"]
    assert accepted, "the fixture composition accepts every outstanding mandate as a gap"
    for row in accepted:
        assert row["gap_accepted"] is True
        assert row["human_rationale"]
        assert row["required"] is True
        assert not [m for m in row["mechanisms"] if m["included"]]


# --- ratifying is not choosing ------------------------------------------------


def test_ratified_and_selected_are_different_words_in_the_document(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    """The distinction the trail makes with two event types survives into the artefact."""
    zone = engine_run["zones"][0]
    zone_id = zone["zone"]["zone_id"]
    capability = next(
        c for c in zone["capabilities"] if len(offered(engine_run, zone_id, c["capability_id"])) > 1
    )
    control = offered(engine_run, zone_id, capability["capability_id"])[0]

    baseline = sign(
        client,
        engine_run,
        choices=[
            *closing_choices(engine_run),
            {
                "kind": "option_selected",
                "zone_id": zone_id,
                "capability_id": capability["capability_id"],
                "control_id": control,
                "rationale": "Prevalece el mecanismo del marco de la zona.",
            },
        ],
    )
    document = statement(client, baseline["baseline_id"])
    chosen = [m for m in mechanisms(document) if m["disposition"] == "selected"]
    ratified = [m for m in mechanisms(document) if m["disposition"] == "ratified"]

    assert [m["control_id"] for m in chosen] == [control]
    assert ratified, "the mandates the engine already covered are ratified, not chosen"
    assert all(m["included"] for m in chosen + ratified)


def test_the_options_nobody_took_stay_in_the_document(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    """Equivalent options side by side is the contribution; a document that hid them
    could not show that there was anything to choose between."""
    baseline = sign(client, engine_run)
    document = statement(client, baseline["baseline_id"])

    assert document["counts"]["offered_not_taken"] > 0
    offered_only = [m for m in mechanisms(document) if m["disposition"] == "offered"]
    assert all(m["included"] is False for m in offered_only)
    assert any(m["framework"] and m["jurisdiction"] for m in offered_only)


def test_a_discarded_option_is_recorded_as_discarded_and_not_dropped(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    zone_id = engine_run["zones"][0]["zone"]["zone_id"]
    capability = next(
        c
        for c in engine_run["zones"][0]["capabilities"]
        if len(offered(engine_run, zone_id, c["capability_id"])) > 1
    )
    controls = offered(engine_run, zone_id, capability["capability_id"])
    reason = "Prevalece el control del marco de la zona; el otro queda descartado por escrito."

    baseline = sign(
        client,
        engine_run,
        choices=[
            *closing_choices(engine_run),
            {
                "kind": "option_selected",
                "zone_id": zone_id,
                "capability_id": capability["capability_id"],
                "control_id": controls[0],
                "rationale": reason,
            },
            {
                "kind": "option_rejected",
                "zone_id": zone_id,
                "capability_id": capability["capability_id"],
                "control_id": controls[1],
                "rationale": reason,
            },
        ],
    )
    document = statement(client, baseline["baseline_id"])
    rejected = [m for m in mechanisms(document) if m["disposition"] == "rejected"]

    assert [m["control_id"] for m in rejected] == [controls[1]]
    assert reason in rejected[0]["rationale"]
    assert document["counts"]["rejected_mechanisms"] == 1


# --- the header, the counts and the evidence ----------------------------------


def test_the_document_declares_the_signature_it_is_about(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    baseline = sign(client, engine_run)
    document = statement(client, baseline["baseline_id"])

    assert document["baseline_id"] == baseline["baseline_id"]
    assert document["run_id"] == baseline["run_id"]
    assert document["profile_id"] == baseline["profile_id"]
    assert document["profile_name"] == baseline["profile_name"]
    assert document["signed_by"] == SIGNATURE["operator"]
    assert document["signed_at"] == baseline["signed_at"]
    assert document["tier_0_complete"] is True


def test_the_versions_that_governed_the_signature_are_the_ones_reported(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    """Projecting rather than recomputing is what makes this true (invariant 3)."""
    baseline = sign(client, engine_run)
    document = statement(client, baseline["baseline_id"])

    assert document["versions"] == baseline["versions"]
    assert document["versions"]["catalog"]


def test_the_document_carries_the_proof_of_the_ledger_it_is_read_from(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    """A declaration read off a ledger nobody can verify is a declaration of trust."""
    baseline = sign(client, engine_run)
    document = statement(client, baseline["baseline_id"])

    assert document["chain"]["valid"] is True
    assert document["chain"]["events"] > 0
    assert document["audit_log_path"] == baseline["audit_log_path"]
    assert client.get(document["audit_log_path"]).status_code == 200


def test_every_row_points_at_the_entries_that_back_it(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    baseline = sign(client, engine_run)
    document = statement(client, baseline["baseline_id"])
    trail = client.get(document["audit_log_path"]).json()
    sequences = {event["sequence"] for event in trail["events"]}

    for row in rows(document):
        assert row["audit_sequences"], row["capability_id"]
        assert set(row["audit_sequences"]) <= sequences


def test_the_counts_agree_with_the_rows_they_count(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    baseline = sign(client, engine_run)
    document = statement(client, baseline["baseline_id"])
    counts = document["counts"]
    all_rows = rows(document)

    assert counts["capabilities"] == len(all_rows)
    assert counts["tier_0"] + counts["tier_1"] == counts["capabilities"]
    assert counts["signed"] == sum(1 for row in all_rows if row["in_signed_baseline"])
    assert counts["accepted_gaps"] == sum(
        1 for row in all_rows if row["outcome"] == "accepted_gap"
    )
    assert counts["included_mechanisms"] == sum(1 for m in mechanisms(document) if m["included"])
    assert sum(
        counts[key]
        for key in (
            "implemented",
            "compensated",
            "deferred",
            "accepted_gaps",
            "open_gaps",
            "roadmap",
        )
    ) == counts["capabilities"]


def test_the_document_says_what_it_is_not(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    """Declared inside the artefact, so it cannot be cited as something it never claimed."""
    baseline = sign(client, engine_run)
    document = statement(client, baseline["baseline_id"])

    assert len(document["limitations"]) >= 3
    assert any("conformidad" in limitation for limitation in document["limitations"])


# --- it is a projection --------------------------------------------------------


def test_asking_for_the_document_records_nothing(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    """No table, no writer: the same argument the sixth endpoint stands on."""
    baseline = sign(client, engine_run)
    before = client.get(baseline["audit_log_path"]).json()["events"]

    statement(client, baseline["baseline_id"])
    statement(client, baseline["baseline_id"], format="oscal")

    after = client.get(baseline["audit_log_path"]).json()["events"]
    assert len(after) == len(before)


def test_the_same_baseline_gives_the_same_document(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    baseline = sign(client, engine_run)
    path = f"{PREFIX}/baseline/{baseline['baseline_id']}/statement"

    assert client.get(path).text == client.get(path).text
    assert client.get(path, params={"format": "oscal"}).text == (
        client.get(path, params={"format": "oscal"}).text
    )


def test_two_baselines_in_one_ledger_do_not_bleed_into_each_other(
    client: TestClient, engine_run: dict[str, Any], offline_candidates: Any
) -> None:
    first = sign(client, engine_run)
    second_run = client.post(f"{PREFIX}/candidates", json={"profile_id": "PROFILE-A"}).json()
    second = sign(client, dict(second_run))

    for baseline in (first, second):
        document = statement(client, baseline["baseline_id"])
        assert document["baseline_id"] == baseline["baseline_id"]
        assert document["run_id"] == baseline["run_id"]


# --- refusals ------------------------------------------------------------------


def test_a_baseline_this_ledger_never_saw_has_no_document(client: TestClient) -> None:
    response = client.get(
        f"{PREFIX}/baseline/00000000-0000-0000-0000-000000000000/statement"
    )
    assert response.status_code == 404
    assert "append-only" in response.json()["detail"]


def test_a_format_the_engine_does_not_emit_is_refused(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    baseline = sign(client, engine_run)
    response = client.get(
        f"{PREFIX}/baseline/{baseline['baseline_id']}/statement", params={"format": "pdf"}
    )
    assert response.status_code == 422
