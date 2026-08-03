"""UCM-15 - `GET /delta`: the query is validated today, the reading lands in UCM-17.

The logic is the next ticket's. What is asserted here is that the contract is not
a placeholder: an unknown jurisdiction, a single region, a repeated one, an
unknown profile and a zone the profile does not declare are all refused *before*
the 501, and both spellings of `regions` that the PRD and the ticket use are
accepted.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.delta.router import RegionsQueryError, parse_regions
from tests.api.conftest import PREFIX

URL = f"{PREFIX}/delta"
DEMO = {"profile_id": "PROFILE-A", "zone_id": "Z-OT-CORRIDOR"}


def test_the_url_the_prd_writes_is_the_url_the_api_parses(client: TestClient) -> None:
    """`?regions=US,EU` — an API that documents a URL it cannot read is worse than two spellings."""
    response = client.get(URL, params={"regions": "US,EU", **DEMO})

    assert response.status_code == 501
    assert "UCM-17" in response.json()["detail"]


def test_repeated_query_parameters_are_read_the_same_way(client: TestClient) -> None:
    response = client.get(URL, params=[("regions", "US"), ("regions", "EU"), *DEMO.items()])
    assert response.status_code == 501


def test_a_single_region_is_not_a_delta(client: TestClient) -> None:
    response = client.get(URL, params={"regions": "US", **DEMO})
    assert response.status_code == 422
    assert "al menos dos" in response.json()["detail"]


def test_an_unknown_jurisdiction_is_refused(client: TestClient) -> None:
    response = client.get(URL, params={"regions": "US,MARS", **DEMO})
    assert response.status_code == 422
    assert "MARS" in response.json()["detail"]


def test_a_repeated_jurisdiction_is_refused(client: TestClient) -> None:
    """`?regions=US,US` is a request nobody meant to write, not a one-region delta."""
    response = client.get(URL, params={"regions": "US,US", **DEMO})
    assert response.status_code == 422
    assert "repetida" in response.json()["detail"]


def test_an_unknown_profile_is_refused(client: TestClient) -> None:
    response = client.get(URL, params={"regions": "US,EU", "profile_id": "P-Z", "zone_id": "Z"})
    assert response.status_code == 422
    assert "P-Z" in response.json()["detail"]


def test_a_zone_the_profile_does_not_declare_is_refused(client: TestClient) -> None:
    response = client.get(
        URL, params={"regions": "US,EU", "profile_id": "PROFILE-A", "zone_id": "Z-NOPE"}
    )
    assert response.status_code == 422
    assert "Z-NOPE" in response.json()["detail"]


def test_the_zone_is_required(client: TestClient) -> None:
    """One zone per call: N zones at once is declared future work, not a default."""
    response = client.get(URL, params={"regions": "US,EU", "profile_id": "PROFILE-A"})
    assert response.status_code == 422


# --- the parser itself --------------------------------------------------------


def test_regions_are_kept_in_the_order_asked_for() -> None:
    assert [region.value for region in parse_regions(["EU,US"])] == ["EU", "US"]


def test_regions_tolerate_spacing_and_case() -> None:
    assert [region.value for region in parse_regions([" us , eu "])] == ["US", "EU"]


def test_an_empty_regions_query_is_refused() -> None:
    with pytest.raises(RegionsQueryError):
        parse_regions([","])
