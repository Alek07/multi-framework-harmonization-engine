from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.repository import AuditRepository
from app.audit.schemas import AuditActor
from app.audit.service import AuditService
from app.candidates.service import CandidatesService
from app.catalog.schemas import Catalog
from tests.api.conftest import PREFIX

URL = f"{PREFIX}/candidates"


def ask(client: TestClient, **body: Any) -> dict[str, Any]:
    response = client.post(URL, json={"profile_id": "PROFILE-A", **body})
    assert response.status_code == 200, response.text
    return dict(response.json())


def every_capability(body: dict[str, Any]) -> list[dict[str, Any]]:
    return [capability for zone in body["zones"] for capability in zone["capabilities"]]


# --- the shape of an answer ---------------------------------------------------


def test_a_profile_comes_back_as_options_per_capability_and_zone(
    client: TestClient, offline_candidates: CandidatesService, catalog: Catalog
) -> None:
    body = ask(client)

    assert body["profile_id"] == "PROFILE-A"
    assert [zone["zone"]["zone_id"] for zone in body["zones"]] == ["Z-OT-CORRIDOR", "Z-SIS"]
    for zone in body["zones"]:
        assert len(zone["capabilities"]) == len(catalog.capabilities)


def test_the_versions_that_governed_the_run_travel_with_it(
    client: TestClient, offline_candidates: CandidatesService, catalog: Catalog
) -> None:
    """Reproducibility is a property of the answer, not of the deployment (invariant 3)."""
    body = ask(client)

    assert body["catalog_version"] == catalog.catalog_version
    assert body["rules_version"]
    assert body["gating_version"]
    assert body["prioritization_version"]


def test_every_option_is_shown_with_what_makes_it_comparable(
    client: TestClient, offline_candidates: CandidatesService
) -> None:
    """Side by side means framework, jurisdiction, strength, mapping type, weight."""
    options = [
        option
        for capability in every_capability(ask(client))
        for option in capability["resolution"]["options"]
    ]
    assert options

    sample = options[0]
    assert {"framework", "jurisdiction", "strength"} <= set(sample["control"])
    assert {"type", "coverage_weight", "provenance"} <= set(sample["mapping"])
    assert sample["status"] in {"eligible", "superseded", "contested"}


def test_a_superseded_candidate_is_marked_and_still_offered(
    client: TestClient, offline_candidates: CandidatesService
) -> None:
    """The core never deletes a candidate, and neither does the API on its way out."""
    for capability in every_capability(ask(client)):
        for option in capability["resolution"]["options"]:
            if option["status"] == "superseded":
                assert option["control"]["id"] in capability["offered_control_ids"]
                assert option["status_reason"]
                return
    raise AssertionError("profile A should supersede at least one candidate by precedence")


# --- invariant 2: nothing is dropped, nothing is silent -----------------------


def test_a_capability_without_candidates_declares_a_gap(
    client: TestClient, offline_candidates: CandidatesService
) -> None:
    for capability in every_capability(ask(client)):
        if capability["offered_control_ids"]:
            continue
        declared = (
            capability["resolution"]["gap"]
            or capability["gating"]["gap"]
            or (capability["retrieval"] or {}).get("gap")
        )
        assert declared, f"{capability['capability_id']} has no candidate and no declared gap"
        assert declared["rationale"]


def test_gating_removes_mechanisms_and_never_the_requirement(
    client: TestClient, offline_candidates: CandidatesService
) -> None:
    for capability in every_capability(ask(client)):
        assert capability["gating"]["required"] is True


def test_retrieval_only_widens_what_the_catalog_offered(
    client: TestClient, offline_candidates: CandidatesService
) -> None:
    body = ask(client)
    assert body["retrieval"]["status"] == "ok"
    assert body["retrieval"]["suggestions"] > 0

    for capability in every_capability(body):
        offered = capability["offered_control_ids"]
        mapped = [option["control"]["id"] for option in capability["resolution"]["options"]]
        assert offered[: len(mapped)] == mapped


def test_switching_retrieval_off_leaves_the_catalog_candidates_intact(
    client: TestClient, offline_candidates: CandidatesService
) -> None:
    widened = ask(client)
    catalog_only = ask(client, retrieval=False)

    assert catalog_only["retrieval"]["status"] == "disabled"
    assert catalog_only["retrieval"]["notice"]
    for zone in catalog_only["zones"]:
        for capability in zone["capabilities"]:
            assert capability["retrieval"] is None
            mapped = [o["control"]["id"] for o in capability["resolution"]["options"]]
            assert capability["offered_control_ids"] == mapped

    # And what was widened really was an addition, never a replacement.
    assert len(_all_offered(widened)) >= len(_all_offered(catalog_only))


def _all_offered(body: dict[str, Any]) -> list[str]:
    return [c for capability in every_capability(body) for c in capability["offered_control_ids"]]


def test_a_declared_lens_reports_everything_it_set_aside(
    client: TestClient, offline_candidates: CandidatesService
) -> None:
    """Apartar no es descartar: a lens is auditable or it is a silent narrowing."""
    body = ask(client, lens={"jurisdictions": ["EU"], "rationale": "lectura europea"})

    assert body["retrieval"]["set_aside"] > 0
    set_aside = [
        candidate
        for capability in every_capability(body)
        for candidate in capability["retrieval"]["set_aside"]
    ]
    assert all(candidate["excluded_by"] for candidate in set_aside)
    assert all(candidate["rationale"] for candidate in set_aside)


# --- the cut carries its rule -------------------------------------------------


def test_the_cut_reaches_the_boundary_with_its_rule_and_its_leftovers(
    client: TestClient, offline_candidates: CandidatesService
) -> None:
    """Cortar no es descartar: the retriever's own bound, auditable at the API."""
    body = ask(client)

    policy = body["retrieval"]["provenance"]["cut_policy"]
    assert policy["version"]
    assert policy["floor"] >= 1 and policy["ceiling"] >= policy["floor"]
    assert policy["framework_cap"] >= 1
    assert body["retrieval"]["below_cut"] >= 0
    assert body["retrieval"]["displaced"] >= 0

    for capability in every_capability(body):
        cut = capability["retrieval"]["cut"]
        if not capability["retrieval"]["retrieved"]:
            assert cut is None
            continue
        assert cut is not None
        assert cut["retained"] + cut["dropped"] == cut["evaluated"]
        if cut["dropped"]:
            assert cut["first_dropped"]["official_id"]
            assert cut["first_dropped"]["rationale"]


def test_the_run_totals_agree_with_the_capabilities_they_summarise(
    client: TestClient, offline_candidates: CandidatesService
) -> None:
    """The two run-level numbers are a rollup, not a second opinion."""
    body = ask(client)

    cuts = [
        capability["retrieval"]["cut"]
        for capability in every_capability(body)
        if capability["retrieval"]["cut"] is not None
    ]

    assert body["retrieval"]["below_cut"] == sum(cut["dropped"] for cut in cuts)
    assert body["retrieval"]["displaced"] == sum(len(cut["displaced"]) for cut in cuts)


def test_what_the_cut_left_out_is_never_also_on_the_screen(
    client: TestClient, offline_candidates: CandidatesService
) -> None:
    body = ask(client)

    for capability in every_capability(body):
        cut = capability["retrieval"]["cut"]
        if cut is None:
            continue
        shown = set(capability["offered_control_ids"])
        assert not (shown & {d["control_id"] for d in cut["displaced"]})


def test_bounding_the_ranking_never_costs_the_catalogs_own_candidates(
    client: TestClient, offline_candidates: CandidatesService
) -> None:
    """The cut is a ranking decision. Coverage is not its to touch."""
    body = ask(client)

    for capability in every_capability(body):
        mapped = [option["control"]["id"] for option in capability["resolution"]["options"]]
        assert capability["offered_control_ids"][: len(mapped)] == mapped


# --- asset-aware suggestions --------------------------------------------------


def test_out_of_sector_norms_are_set_aside_without_any_lens(
    client: TestClient, offline_candidates: CandidatesService
) -> None:
    """The engine applies the zone's sectoral applicability on its own initiative.

    PROFILE-A operates in energy, so the maritime (IMO) norms are set aside on the
    sector axis — not silently dropped, and not offered as if they applied — with
    no operator lens in the request at all.
    """
    body = ask(client)

    assert body["retrieval"]["set_aside"] > 0
    set_aside = [
        candidate
        for capability in every_capability(body)
        for candidate in capability["retrieval"]["set_aside"]
    ]
    assert any("sector" in candidate["excluded_by"] for candidate in set_aside)
    assert all(candidate["rationale"] for candidate in set_aside)


def test_a_suggestion_never_contradicts_a_gating_exclusion(
    client: TestClient, offline_candidates: CandidatesService
) -> None:
    """Acceptance: a suggestion for a mechanism gating ruled out of the zone says so."""
    body = ask(client)

    for zone in body["zones"]:
        gated = {
            decision["control_id"]
            for capability in zone["capabilities"]
            for decision in capability["gating"]["excluded"]
        }
        for capability in zone["capabilities"]:
            for hit in capability["retrieval"]["retrieved"]:
                if hit["relation"] != "widens":
                    continue
                if hit["control"]["id"] in gated:
                    assert hit["gated_out"] is not None
                    assert hit["gated_out"]["zone_id"] == zone["zone"]["zone_id"]
                else:
                    assert hit["gated_out"] is None


# --- degradation is declared, never silent ------------------------------------


def test_a_machine_without_qdrant_still_gets_the_deterministic_baseline(
    client: TestClient, candidates_without_index: CandidatesService
) -> None:
    body = ask(client)

    assert body["retrieval"]["status"] == "unavailable"
    assert "índice del catálogo no está disponible" in body["retrieval"]["notice"]
    assert body["zones"]
    assert any(capability["offered_control_ids"] for capability in every_capability(body))


def test_explanations_are_not_attempted_without_the_retrieval_pass(
    client: TestClient, offline_candidates: CandidatesService
) -> None:
    body = ask(
        client,
        retrieval=False,
        explain={"zone_id": "Z-SIS", "capability_ids": ["CAP-PR-MFA"]},
    )
    assert body["explanations_notice"]
    assert all(capability["explanations"] is None for capability in every_capability(body))


# --- invariant 5: the run is on the record ------------------------------------


async def test_the_engine_run_is_in_the_ledger_before_the_response_leaves(
    client: TestClient, offline_candidates: CandidatesService, db: AsyncSession
) -> None:
    body = ask(client)

    assert body["audit_events"] > 0
    events = await AuditRepository(db).by_run(UUID(body["run_id"]))
    assert len(events) == body["audit_events"]
    assert {event.actor for event in events} == {AuditActor.ENGINE}


async def test_the_recorded_run_is_a_chain_that_verifies(
    client: TestClient, offline_candidates: CandidatesService, db: AsyncSession
) -> None:
    body = ask(client)
    verification = await AuditService(AuditRepository(db)).verify_run(UUID(body["run_id"]))
    assert verification.valid, verification.detail


async def test_the_rag_pass_is_recorded_as_an_engine_decision_too(
    client: TestClient, offline_candidates: CandidatesService, db: AsyncSession
) -> None:
    body = ask(client)
    stages = {event.stage.value for event in await AuditRepository(db).by_run(UUID(body["run_id"]))}
    assert "retrieval" in stages


async def test_two_calls_are_two_runs(
    client: TestClient, offline_candidates: CandidatesService, db: AsyncSession
) -> None:
    first, second = ask(client), ask(client)
    assert first["run_id"] != second["run_id"]


# --- the explanation layer is presentational ----------------------------------


def test_explanations_are_returned_only_for_the_capabilities_asked_about(
    client: TestClient, explainable: dict[str, Any]
) -> None:
    body = ask(
        client,
        explain={
            "zone_id": explainable["zone_id"],
            "capability_ids": [explainable["capability_id"]],
        },
    )

    explained = [c for c in every_capability(body) if c["explanations"] is not None]
    assert len(explained) == 1
    assert explained[0]["capability_id"] == explainable["capability_id"]
    assert explained[0]["zone_id"] == explainable["zone_id"]


def test_an_explanation_never_adds_drops_or_reorders_a_candidate(
    client: TestClient, explainable: dict[str, Any]
) -> None:
    body = ask(
        client,
        explain={
            "zone_id": explainable["zone_id"],
            "capability_ids": [explainable["capability_id"]],
        },
    )
    capability = next(c for c in every_capability(body) if c["explanations"] is not None)
    explanations = capability["explanations"]

    assert explanations["presentational"] is True
    assert [e["control_id"] for e in explanations["explanations"]] == explainable["offered"]
    assert capability["offered_control_ids"] == explainable["offered"]
    assert all(e["status"] == "generated" for e in explanations["explanations"])


def test_an_unknown_zone_in_the_explain_scope_is_refused(
    client: TestClient, offline_candidates: CandidatesService
) -> None:
    response = client.post(
        URL,
        json={
            "profile_id": "PROFILE-A",
            "explain": {"zone_id": "Z-NOPE", "capability_ids": ["CAP-PR-MFA"]},
        },
    )
    assert response.status_code == 422
    assert "Z-NOPE" in response.json()["detail"]


def test_an_unknown_capability_in_the_explain_scope_is_refused(
    client: TestClient, offline_candidates: CandidatesService
) -> None:
    response = client.post(
        URL,
        json={
            "profile_id": "PROFILE-A",
            "explain": {"zone_id": "Z-SIS", "capability_ids": ["CAP-NOPE"]},
        },
    )
    assert response.status_code == 422
    assert "CAP-NOPE" in response.json()["detail"]


def test_an_empty_explain_scope_is_refused(
    client: TestClient, offline_candidates: CandidatesService
) -> None:
    """"Explain nothing" is not a request; "explain everything" is not a default."""
    response = client.post(
        URL,
        json={"profile_id": "PROFILE-A", "explain": {"zone_id": "Z-SIS", "capability_ids": []}},
    )
    assert response.status_code == 422


# --- naming the profile -------------------------------------------------------


def test_an_inline_profile_is_accepted(
    client: TestClient, offline_candidates: CandidatesService
) -> None:
    from app.assets.loader import get_profile

    response = client.post(
        URL, json={"profile": get_profile("PROFILE-B").model_dump(mode="json")}
    )
    assert response.status_code == 200, response.text
    assert response.json()["profile_id"] == "PROFILE-B"


def test_naming_the_profile_twice_is_refused(
    client: TestClient, offline_candidates: CandidatesService
) -> None:
    from app.assets.loader import get_profile

    response = client.post(
        URL,
        json={
            "profile": get_profile("PROFILE-B").model_dump(mode="json"),
            "profile_id": "PROFILE-A",
        },
    )
    assert response.status_code == 422
    assert "no ambos" in response.json()["detail"]


def test_not_naming_the_profile_at_all_is_refused(
    client: TestClient, offline_candidates: CandidatesService
) -> None:
    response = client.post(URL, json={})
    assert response.status_code == 422
    assert "Falta el perfil" in response.json()["detail"]


def test_an_unknown_profile_id_is_refused(
    client: TestClient, offline_candidates: CandidatesService
) -> None:
    response = client.post(URL, json={"profile_id": "PROFILE-Z"})
    assert response.status_code == 422
    assert "PROFILE-Z" in response.json()["detail"]
