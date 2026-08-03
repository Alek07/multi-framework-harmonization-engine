"""UCM-15 - Invariant 4, measured: the API is five endpoints, and no more.

"Any additional endpoint is scope creep unless justified in writing" is the kind
of rule that erodes one convenient route at a time. These tests are what make it
cost something: adding an endpoint without editing `SURFACE` fails the suite, and
editing `SURFACE` is a visible act in the diff.

The comparison is made against the **OpenAPI document**, not the router objects,
for two reasons. It is what a client — and the Swagger demo that is the declared
plan B if the UI is cut — actually sees, and it is the level at which a route
mounted by accident becomes real.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.router import SURFACE
from tests.api.conftest import PREFIX

HEALTH = ("GET", f"{PREFIX}/health")


def mounted(client: TestClient) -> set[tuple[str, str]]:
    schema = client.get(f"{PREFIX}/openapi.json").json()
    return {
        (method.upper(), path)
        for path, operations in schema["paths"].items()
        for method in operations
    }


def test_the_api_is_exactly_the_five_declared_endpoints(client: TestClient) -> None:
    declared = {(method, f"{PREFIX}{path}") for method, path in SURFACE}
    assert mounted(client) - {HEALTH} == declared


def test_the_five_endpoints_are_the_ones_the_prd_names(client: TestClient) -> None:
    assert SURFACE == (
        ("POST", "/asset/parse"),
        ("POST", "/candidates"),
        ("POST", "/baseline/compose"),
        ("GET", "/baseline/{baseline_id}/audit-log"),
        ("POST", "/delta"),
    )
    assert len(SURFACE) == 5


def test_every_engine_endpoint_can_name_the_asset_the_same_way(client: TestClient) -> None:
    """The three endpoints that read a profile accept it inline or by id, alike.

    This is the property the delta's method change bought. An endpoint that could
    only take `profile_id` could only ever be asked about the profiles frozen in
    the repository — never about the asset the operator has just described,
    reviewed and composed, which is the whole point of the engine.
    """
    schema = client.get(f"{PREFIX}/openapi.json").json()
    components = schema["components"]["schemas"]

    for path, body in (
        (f"{PREFIX}/candidates", "CandidatesRequest"),
        (f"{PREFIX}/baseline/compose", "ComposeRequest"),
        (f"{PREFIX}/delta", "DeltaRequest"),
    ):
        assert "post" in schema["paths"][path], f"{path} takes no body"
        properties = components[body]["properties"]
        assert "profile" in properties, f"{body} cannot carry a reviewed profile"
        assert "profile_id" in properties, f"{body} cannot name a frozen profile"


def test_health_is_served_but_is_not_part_of_the_surface(client: TestClient) -> None:
    """A liveness probe for the compose healthcheck (UCM-20), not a function of the engine."""
    assert client.get(f"{PREFIX}/health").status_code == 200
    assert HEALTH in mounted(client)
    assert HEALTH not in {(method, f"{PREFIX}{path}") for method, path in SURFACE}


def test_every_endpoint_is_documented(client: TestClient) -> None:
    """Swagger is the declared plan B for the demo, so it has to read like one."""
    schema = client.get(f"{PREFIX}/openapi.json").json()
    for method, path in SURFACE:
        operation = schema["paths"][f"{PREFIX}{path}"][method.lower()]
        assert operation.get("summary"), f"{method} {path} has no summary"
        assert operation.get("description"), f"{method} {path} has no description"
