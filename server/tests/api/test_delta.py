"""UCM-15/UCM-17 - `POST /delta`: one zone, two readings, and what changes between them.

The request validation was written with the contract in UCM-15 and still stands;
what moved (UCM-21) is that the asset is named in a body, inline or by id, like
every other engine endpoint — so the delta can be asked about the asset the
operator just composed and not only about the profiles frozen in the repo. The
rest asserts the reading itself, and it is written about the claims the demo makes:

* **The `+` is cumulative.** "+EU" is the US reading *plus* the European obligation
  overlay — never a parallel catalog in which a European operator has no CIS and no
  CSF. Every jurisdiction not under comparison is common ground in both readings.
* **A lens sets candidates aside, it never deletes them.** The US reading reports
  the NIS2 articles it left out, by name, before "+EU" adds them.
* **What +EU adds is exigencia, not coverage** — and the response has to say so.
  Every NIS2 mapping in this catalog is contextual with a low weight, so a delta
  that only reported coverage would look empty when it is not, and one that only
  reported the extra control would suggest a technical gap that does not exist.
* **Nothing regional is invented.** The gaps the deterministic core declares from
  the common ground are identical in both readings and are not counted as regional.

Everything here runs offline: the delta reads authored mappings, not vectors.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.loader import get_profile
from app.audit.repository import AuditRepository
from app.delta.router import RegionsQueryError, parse_regions
from tests.api.conftest import PREFIX

URL = f"{PREFIX}/delta"
# The demo zone and region pair fixed in UCM-3: the engineering station is where
# the US<->EU divergence is real and legible, not the pure OT corridor.
DEMO: dict[str, Any] = {
    "regions": ["US", "EU"],
    "profile_id": "PROFILE-B",
    "zone_id": "Z-ENG-STATION",
}

# The capabilities that carry the delta. UCM-3 named five, against a catalog that
# held NIS2 as three whole articles; v0.2.0 breaks art. 21(2) into its ten measures
# (UCM-43), so the European overlay now lands on sixteen. That widening *is* the
# regional delta getting sharper — "el art. 21 aplica" told the operator nothing
# about which obligation was missing.
NIS2_CAPABILITIES = {
    "CAP-GOV-OVERSIGHT",
    "CAP-GOV-POLICY",
    "CAP-GOV-RISK",
    "CAP-GOV-ROLES",
    "CAP-GOV-SUPPLY",
    "CAP-ID-ASSET",
    "CAP-ID-THREAT",
    "CAP-PR-ACCESS",
    "CAP-PR-AWARENESS",
    "CAP-PR-BACKUP",
    "CAP-PR-CRYPTO",
    "CAP-PR-MFA",
    "CAP-PR-PATCH",
    "CAP-RC-RECOVER",
    "CAP-RS-IR",
    "CAP-RS-REPORT",
}


def ask(client: TestClient, **body: Any) -> dict[str, Any]:
    response = client.post(URL, json={**DEMO, **body})
    assert response.status_code == 200, response.text
    return dict(response.json())


# --- the reading --------------------------------------------------------------


def test_the_demo_zone_reads_under_both_regions(client: TestClient) -> None:
    body = ask(client)

    assert body["profile_id"] == "PROFILE-B"
    assert body["zone"]["zone_id"] == "Z-ENG-STATION"
    assert body["regions"] == ["US", "EU"]
    assert len(body["capabilities"]) == 37


def test_the_readings_are_cumulative_over_common_ground(client: TestClient) -> None:
    """"+EU" is the US reading plus NIS2 — not a catalog where Europe has no CIS."""
    body = ask(client)

    assert body["common_jurisdictions"] == ["INTL", "INTL-MARITIME"]
    for capability in body["capabilities"]:
        us, plus_eu = capability["regions"]
        assert us["label"] == "US"
        assert plus_eu["label"] == "+EU"
        assert us["jurisdictions"] == ["US", "INTL", "INTL-MARITIME"]
        assert plus_eu["jurisdictions"] == ["US", "EU", "INTL", "INTL-MARITIME"]
        # Cumulative by construction: the later reading never loses a candidate.
        assert set(us["offered_control_ids"]) <= set(plus_eu["offered_control_ids"])


def test_each_reading_declares_the_lens_it_used(client: TestClient) -> None:
    body = ask(client)

    assert len(body["lenses"]) == 2
    assert body["lenses"][0]["jurisdictions"] == ["US", "INTL", "INTL-MARITIME"]
    assert all("acumulativas" in lens["rationale"] for lens in body["lenses"])


def test_the_delta_falls_on_the_capabilities_ucm3_named(client: TestClient) -> None:
    body = ask(client)

    assert set(body["changed_capability_ids"]) == NIS2_CAPABILITIES
    assert len(body["unchanged_capability_ids"]) == 37 - len(NIS2_CAPABILITIES)


def test_what_plus_eu_adds_is_obligation_and_not_coverage(client: TestClient) -> None:
    """The finding of the demo, and the one a coverage number alone would hide."""
    body = ask(client)

    for capability_id in body["changed_capability_ids"]:
        capability = next(
            c for c in body["capabilities"] if c["capability_id"] == capability_id
        )
        us, plus_eu = capability["regions"]

        assert capability["added"], capability_id
        assert capability["changes_coverage"] is False
        assert us["coverage"] == plus_eu["coverage"]
        for added in capability["added"]:
            assert added["framework"] == "NIS2"
            assert added["jurisdiction"] == "EU"
            assert added["mapping_type"] == "contextual"
            assert added["changes_coverage"] is False
            assert added["strength"]
            assert "exigencia, no mecanismo" in added["rationale"]


def test_the_notification_deadlines_are_the_headline_of_the_delta(
    client: TestClient,
) -> None:
    """NIS2 Art. 23: 24 h / 72 h / one month over a capability CSF already covers."""
    capability = next(
        c
        for c in ask(client)["capabilities"]
        if c["capability_id"] == "CAP-RS-REPORT"
    )
    added = capability["added"][0]

    assert added["official_id"] == "Art. 23"
    assert "24h/72h" in added["strength"]
    assert "CTL-CSF-RSCO02" in capability["common_control_ids"]
    assert "obligación legal" in capability["rationale"]


def test_an_unchanged_capability_says_so_plainly(client: TestClient) -> None:
    body = ask(client)
    capability = next(
        c
        for c in body["capabilities"]
        if c["capability_id"] in body["unchanged_capability_ids"]
    )

    assert capability["added"] == []
    assert capability["changed"] is False
    assert "idéntica en todas las lecturas" in capability["rationale"]


# --- nothing is restricted, nothing is invented -------------------------------


def test_the_first_reading_reports_what_its_lens_set_aside(client: TestClient) -> None:
    """Apartar no es descartar: the US reading names the NIS2 articles it left out."""
    body = ask(client)

    for capability_id in body["changed_capability_ids"]:
        capability = next(
            c for c in body["capabilities"] if c["capability_id"] == capability_id
        )
        us, plus_eu = capability["regions"]
        assert us["set_aside_control_ids"], capability_id
        assert set(us["set_aside_control_ids"]) == set(plus_eu["only_here_control_ids"])
        assert plus_eu["set_aside_control_ids"] == []
        assert "Apartar" in us["rationale"]


def test_the_starting_reading_contributes_nothing_exclusive(client: TestClient) -> None:
    """It is the baseline of the comparison: everything it offers, "+EU" offers too."""
    for capability in ask(client)["capabilities"]:
        us = capability["regions"][0]
        assert us["only_here_control_ids"] == []
        assert "lectura de partida" in us["rationale"]


def test_the_union_of_the_readings_is_the_whole_catalog_offer(client: TestClient) -> None:
    """A jurisdiction not under comparison is common ground, never a dropped one."""
    body = ask(client)

    for capability in body["capabilities"]:
        offered = set(capability["regions"][-1]["offered_control_ids"])
        set_aside = set(capability["regions"][-1]["set_aside_control_ids"])
        assert set_aside == set()
        assert offered >= set(capability["common_control_ids"])


def test_a_gap_that_both_readings_share_is_not_a_regional_gap(client: TestClient) -> None:
    """Partial coverage comes from the common ground; calling it regional would be false."""
    body = ask(client)

    assert body["regional_gap_capability_ids"] == []
    with_gaps = [
        c["capability_id"]
        for c in body["capabilities"]
        if any(view["gap"] is not None for view in c["regions"])
    ]
    assert with_gaps, "the core declares residual gaps in this zone"
    for capability_id in with_gaps:
        capability = next(
            c for c in body["capabilities"] if c["capability_id"] == capability_id
        )
        # Same gap under both readings — which is exactly why it is not regional.
        kinds = {
            view["gap"]["kind"] if view["gap"] else None for view in capability["regions"]
        }
        assert len(kinds) == 1


async def test_a_delta_is_a_view_and_writes_nothing(
    client: TestClient, db: AsyncSession
) -> None:
    """It decides nothing and belongs to no run, so it belongs in no ledger entry."""
    ask(client)
    assert await AuditRepository(db).count() == 0


def test_the_delta_needs_no_ai_at_all(client: TestClient) -> None:
    """No candidates fixture, no index, no model: it reads authored mappings."""
    body = ask(client)
    assert body["catalog_version"]
    assert body["rules_version"]


# --- the order of the regions is the question being asked ---------------------


def test_reversing_the_regions_asks_a_different_question(client: TestClient) -> None:
    forward = ask(client, regions=["US", "EU"])
    backward = ask(client, regions=["EU", "US"])

    assert [r["label"] for r in forward["capabilities"][0]["regions"]] == ["US", "+EU"]
    assert [r["label"] for r in backward["capabilities"][0]["regions"]] == ["EU", "+US"]
    # Same union, different starting point — and the delta lands elsewhere.
    assert set(backward["changed_capability_ids"]) != set(forward["changed_capability_ids"])


# --- the asset the delta is about ---------------------------------------------


def test_the_delta_answers_about_an_asset_that_is_in_no_repository(
    client: TestClient,
) -> None:
    """The reason the endpoint takes a body at all (UCM-21).

    An operator describes an asset, reviews the drafted profile and composes its
    baseline; the asset has no id in `data/profiles` and never will. Asking what
    changes under EU obligation is the same question for that asset as for a
    frozen one, and the engine has to be able to answer it.
    """
    frozen = get_profile("PROFILE-B")
    composed = frozen.model_copy(update={"id": "ASSET-PUENTE-DE-MANDO", "name": "Puente"})

    body = ask(client, profile=composed.model_dump(mode="json"), profile_id=None)

    assert body["profile_id"] == "ASSET-PUENTE-DE-MANDO"
    assert body["zone"]["zone_id"] == "Z-ENG-STATION"
    # Same asset, same catalog, same rules: the reading does not depend on where
    # the profile was stored.
    assert body["changed_capability_ids"] == ask(client)["changed_capability_ids"]


def test_naming_the_profile_twice_is_refused(client: TestClient) -> None:
    """The engine does not choose its own input (`requested_profile`)."""
    response = client.post(
        URL, json={**DEMO, "profile": get_profile("PROFILE-B").model_dump(mode="json")}
    )
    assert response.status_code == 422
    assert "no ambos" in response.json()["detail"]


def test_naming_no_profile_at_all_is_refused(client: TestClient) -> None:
    response = client.post(URL, json={"regions": ["US", "EU"], "zone_id": "Z-ENG-STATION"})
    assert response.status_code == 422
    assert "Falta el perfil" in response.json()["detail"]


# --- the request contract (UCM-15) --------------------------------------------


def test_the_comma_form_of_the_prd_is_read_the_same_way(client: TestClient) -> None:
    """`regions: ["US,EU"]` is the spelling the PRD and the ticket use."""
    response = client.post(URL, json={**DEMO, "regions": ["US,EU"]})
    assert response.status_code == 200
    assert response.json()["regions"] == ["US", "EU"]


def test_a_single_region_is_not_a_delta(client: TestClient) -> None:
    response = client.post(URL, json={**DEMO, "regions": ["US"]})
    assert response.status_code == 422
    assert "al menos dos" in response.json()["detail"]


def test_an_unknown_jurisdiction_is_refused(client: TestClient) -> None:
    response = client.post(URL, json={**DEMO, "regions": ["US", "MARS"]})
    assert response.status_code == 422
    assert "MARS" in response.json()["detail"]


def test_a_repeated_jurisdiction_is_refused(client: TestClient) -> None:
    """`US,US` is a request nobody meant to write, not a one-region delta."""
    response = client.post(URL, json={**DEMO, "regions": ["US", "US"]})
    assert response.status_code == 422
    assert "repetida" in response.json()["detail"]


def test_an_unknown_profile_is_refused(client: TestClient) -> None:
    response = client.post(URL, json={**DEMO, "profile_id": "P-Z"})
    assert response.status_code == 422
    assert "P-Z" in response.json()["detail"]


def test_a_zone_the_profile_does_not_declare_is_refused(client: TestClient) -> None:
    response = client.post(URL, json={**DEMO, "zone_id": "Z-NOPE"})
    assert response.status_code == 422
    assert "Z-NOPE" in response.json()["detail"]


def test_the_zone_is_required(client: TestClient) -> None:
    """One zone per call: N zones at once is declared future work, not a default."""
    response = client.post(URL, json={"regions": ["US", "EU"], "profile_id": "PROFILE-B"})
    assert response.status_code == 422


# --- the parser itself --------------------------------------------------------


def test_regions_are_kept_in_the_order_asked_for() -> None:
    assert [region.value for region in parse_regions(["EU,US"])] == ["EU", "US"]


def test_regions_tolerate_spacing_and_case() -> None:
    assert [region.value for region in parse_regions([" us , eu "])] == ["US", "EU"]


def test_an_empty_regions_query_is_refused() -> None:
    with pytest.raises(RegionsQueryError):
        parse_regions([","])
