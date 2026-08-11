"""UCM-21 - `GET /baselines`: what has been signed here, read from the ledger.

The sixth endpoint exists because the other five all take the composition as their
subject and none of them can answer that question — the two that mention a
baseline take its id, which only the client that signed it has. These tests are
written about the property that makes the addition defensible rather than merely
convenient:

* **It stores nothing.** The list comes back from an empty ledger empty, fills as
  compositions are signed, and every field of every entry can be found again in
  that baseline's own trail. There is no second place where a baseline lives, so
  there is nothing that can drift from the trail.
* **It counts what the operator did, from the entries that record it.** Gaps
  accepted and conflicts settled are tallied over the human's own entries, not
  taken from a number the same composition wrote about itself.
* **Newest first**, in the ledger's order rather than by timestamp: two baselines
  signed inside the same second still have an order, and it is the order they were
  written in.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient

from app.candidates.service import CandidatesService
from tests.api.conftest import PREFIX
from tests.api.test_compose import SIGNATURE, closing_choices, offered, sign

BASELINES = f"{PREFIX}/baselines"


def listed(client: TestClient) -> dict[str, Any]:
    response = client.get(BASELINES)
    assert response.status_code == 200, response.text
    return dict(response.json())


def entry_for(client: TestClient, baseline_id: str) -> dict[str, Any]:
    return next(b for b in listed(client)["baselines"] if b["baseline_id"] == baseline_id)


# --- an empty ledger ----------------------------------------------------------


def test_a_ledger_with_no_signature_lists_nothing_and_says_so(client: TestClient) -> None:
    """Nothing signed is an answer, not a missing resource: 200 with an empty list."""
    body = listed(client)

    assert body["baselines"] == []
    assert body["total"] == 0
    assert "ninguna" in body["rationale"]


# --- what a signed baseline looks like in the list ----------------------------


def test_a_signed_baseline_appears_in_the_list(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    baseline = sign(client, engine_run)
    body = listed(client)

    assert body["total"] == 1
    (summary,) = body["baselines"]
    assert summary["baseline_id"] == baseline["baseline_id"]
    assert summary["run_id"] == baseline["run_id"]
    assert summary["profile_id"] == "PROFILE-A"
    assert summary["signed_by"] == SIGNATURE["operator"]
    assert summary["tier_0_complete"] is True


def test_the_summary_agrees_with_the_baseline_it_summarises(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    """The list is a reading of the ledger, so it cannot say anything else than the trail."""
    baseline = sign(client, engine_run)
    summary = entry_for(client, baseline["baseline_id"])

    assert summary["profile_name"] == baseline["profile_name"]
    assert summary["versions"] == baseline["versions"]
    assert summary["zone_ids"] == [zone["zone_id"] for zone in baseline["zones"]]
    assert summary["audit_events"] == baseline["audit_events"]
    assert summary["audit_log_path"] == baseline["audit_log_path"]


def test_the_summary_points_at_a_trail_that_can_be_read(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    """A list of signatures whose evidence cannot be reached would be a list of claims."""
    sign(client, engine_run)
    (summary,) = listed(client)["baselines"]

    trail = client.get(summary["audit_log_path"])
    assert trail.status_code == 200
    assert trail.json()["chain"]["valid"] is True


def test_the_signature_is_dated_in_utc_on_the_wire(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    """SQLite drops the offset; a naive timestamp is one the browser reads as local time.

    Left unnormalised this is invisible in the API and wrong in the interface: the
    list would date a signature up to a day away from what `POST /baseline/compose`
    said about the very same baseline.
    """
    baseline = sign(client, engine_run)
    (summary,) = listed(client)["baselines"]

    signed_at = datetime.fromisoformat(summary["signed_at"])
    assert signed_at.tzinfo is not None, f"naive timestamp on the wire: {summary['signed_at']}"
    assert signed_at.utcoffset() == timedelta(0)
    assert signed_at == datetime.fromisoformat(baseline["signed_at"])


def test_the_operators_own_justification_is_what_is_listed(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    """What a reviewer has to read is the sentence that was signed, not a rendering of it."""
    sign(client, engine_run)
    (summary,) = listed(client)["baselines"]

    assert SIGNATURE["rationale"] in summary["signature_rationale"]


# --- the tallies --------------------------------------------------------------


def test_the_gaps_the_human_accepted_are_counted_from_their_own_entries(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    """Every mandate of the fixture composition is closed by accepting the gap in writing."""
    accepted = sum(len(zone["outstanding_capability_ids"]) for zone in engine_run["zones"])
    assert accepted > 0, "the fixture run should leave mandates for the human to close"

    sign(client, engine_run)
    (summary,) = listed(client)["baselines"]

    assert summary["gaps_accepted"] == accepted
    assert summary["human_choices"] == accepted
    assert summary["conflicts_resolved"] == 0


def test_settling_a_conflict_is_counted_as_one(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    """Choosing one equivalent and discarding another is one settled conflict on the record."""
    zone = engine_run["zones"][0]
    zone_id = zone["zone"]["zone_id"]
    capability = next(
        c for c in zone["capabilities"] if len(offered(engine_run, zone_id, c["capability_id"])) > 1
    )
    controls = offered(engine_run, zone_id, capability["capability_id"])
    reason = "Prevalece el control del marco de la zona; el otro queda descartado por escrito."

    sign(
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
    (summary,) = listed(client)["baselines"]

    assert summary["conflicts_resolved"] == 1


def test_the_mandates_the_engine_could_not_close_travel_with_the_summary(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    """A baseline signed over open mandates is one a reviewer must be able to spot in the list."""
    sign(client, engine_run)
    (summary,) = listed(client)["baselines"]

    expected = {
        zone["zone"]["zone_id"]: zone["outstanding_capability_ids"]
        for zone in engine_run["zones"]
        if zone["outstanding_capability_ids"]
    }
    assert summary["closed_mandates"] == expected


# --- order --------------------------------------------------------------------


def test_baselines_come_back_newest_first(
    client: TestClient, engine_run: dict[str, Any], offline_candidates: CandidatesService
) -> None:
    first = sign(client, engine_run)

    second_run = client.post(f"{PREFIX}/candidates", json={"profile_id": "PROFILE-A"})
    assert second_run.status_code == 200, second_run.text
    second = sign(client, dict(second_run.json()))

    ids = [b["baseline_id"] for b in listed(client)["baselines"]]
    assert ids == [second["baseline_id"], first["baseline_id"]]


def test_each_baseline_only_counts_its_own_entries(
    client: TestClient, engine_run: dict[str, Any], offline_candidates: CandidatesService
) -> None:
    """Two compositions in one ledger: the tallies must not bleed from one into the other."""
    sign(client, engine_run)

    second_run = client.post(f"{PREFIX}/candidates", json={"profile_id": "PROFILE-A"})
    sign(client, dict(second_run.json()))

    body = listed(client)
    assert body["total"] == 2
    assert len({b["baseline_id"] for b in body["baselines"]}) == 2
    for summary in body["baselines"]:
        trail = client.get(summary["audit_log_path"]).json()
        stamped = [e for e in trail["events"] if e["baseline_id"] == summary["baseline_id"]]
        assert summary["audit_events"] == len(stamped)
