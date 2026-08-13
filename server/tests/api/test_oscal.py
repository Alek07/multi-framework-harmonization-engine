"""UCM-46 - The same declaration as a partial OSCAL SSP: what it claims and what it does not.

The value of this export is only as good as its honesty, so that is what is
asserted here: the blocks OSCAL requires are present, every state comes from the
model's own vocabulary, everything the model does not define is namespaced as an
extension instead of being smuggled into a core field, and the one case the model
has no state for — a gap accepted in writing — is flagged rather than smoothed
over. Plus the property the whole POC rests on: the same baseline exports to the
same bytes, ids included.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi.testclient import TestClient

from app.baseline.oscal import NS, OSCAL_VERSION
from tests.api.conftest import PREFIX
from tests.api.test_compose import closing_choices, sign

# The five states the SSP model defines for an implemented requirement.
CORE_STATES = {"implemented", "partial", "planned", "alternative", "not-applicable"}


def ssp(client: TestClient, baseline_id: str) -> dict[str, Any]:
    response = client.get(
        f"{PREFIX}/baseline/{baseline_id}/statement", params={"format": "oscal"}
    )
    assert response.status_code == 200, response.text
    return dict(response.json())["system-security-plan"]


def requirements(plan: dict[str, Any]) -> list[dict[str, Any]]:
    return list(plan["control-implementation"]["implemented-requirements"])


def by_components(plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [entry for requirement in requirements(plan) for entry in requirement["by-components"]]


def walk(node: Any) -> Any:
    """Every value in the document, so a whole-document property can be asserted."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield key, value
            yield from walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from walk(item)


# --- the shape OSCAL asks for --------------------------------------------------


def test_the_export_has_the_blocks_the_ssp_model_requires(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    baseline = sign(client, engine_run)
    plan = ssp(client, baseline["baseline_id"])

    for block in (
        "uuid",
        "metadata",
        "import-profile",
        "system-characteristics",
        "system-implementation",
        "control-implementation",
    ):
        assert block in plan, block

    metadata = plan["metadata"]
    assert {"title", "last-modified", "version", "oscal-version"} <= set(metadata)
    assert metadata["oscal-version"] == OSCAL_VERSION

    characteristics = plan["system-characteristics"]
    assert {
        "system-ids",
        "system-name",
        "description",
        "system-information",
        "status",
        "authorization-boundary",
    } <= set(characteristics)
    assert characteristics["system-information"]["information-types"]
    assert plan["system-implementation"]["users"]
    assert plan["system-implementation"]["components"]


def test_no_field_is_present_and_null(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    """An absent OSCAL field is absent; `null` would fail validation for nothing."""
    baseline = sign(client, engine_run)
    plan = ssp(client, baseline["baseline_id"])

    assert not [key for key, value in walk(plan) if value is None]


def test_every_uuid_in_the_document_is_one(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    baseline = sign(client, engine_run)
    plan = ssp(client, baseline["baseline_id"])

    # `uuid` is a string and `party-uuids` a list of them: both end in "uuid".
    identifiers = [value for key, value in walk(plan) if key.endswith("uuid")]
    flattened = [
        item
        for value in identifiers
        for item in ([value] if isinstance(value, str) else value)
    ]
    assert flattened
    for identifier in flattened:
        assert UUID(identifier)
    assert plan["uuid"] == baseline["baseline_id"]


# --- what the mapping says -----------------------------------------------------


def test_the_control_is_the_capability_and_the_component_is_the_zone(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    baseline = sign(client, engine_run)
    plan = ssp(client, baseline["baseline_id"])
    document = client.get(f"{PREFIX}/baseline/{baseline['baseline_id']}/statement").json()

    capabilities = {row["capability_id"] for zone in document["zones"] for row in zone["rows"]}
    assert {r["control-id"] for r in requirements(plan)} == capabilities

    components = {component["uuid"] for component in plan["system-implementation"]["components"]}
    assert len(components) == len(document["zones"])
    assert {entry["component-uuid"] for entry in by_components(plan)} <= components


def test_every_capability_of_every_zone_reaches_the_export(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    """0 silent omissions survives the translation into a foreign schema."""
    baseline = sign(client, engine_run)
    plan = ssp(client, baseline["baseline_id"])
    document = client.get(f"{PREFIX}/baseline/{baseline['baseline_id']}/statement").json()

    expected = sum(len(zone["rows"]) for zone in document["zones"])
    assert len(by_components(plan)) == expected


def test_only_the_models_own_states_are_used(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    baseline = sign(client, engine_run)
    plan = ssp(client, baseline["baseline_id"])

    states = {entry["implementation-status"]["state"] for entry in by_components(plan)}
    assert states
    assert states <= CORE_STATES


def test_everything_the_model_does_not_define_is_namespaced_as_an_extension(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    """OSCAL prescribes a namespace for this; inventing core names would be a lie."""
    baseline = sign(client, engine_run)
    plan = ssp(client, baseline["baseline_id"])

    properties = [value for key, value in walk(plan) if key == "props"]
    flattened = [prop for group in properties for prop in group]
    assert flattened
    assert all(prop["ns"] == NS for prop in flattened)
    assert NS.startswith("urn:")


def test_a_compensatory_control_is_exported_as_an_alternative_implementation(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    """The one place the core vocabulary fits the engine exactly."""
    zone = engine_run["zones"][0]
    zone_id = zone["zone"]["zone_id"]
    outstanding = zone["outstanding_capability_ids"]
    assert outstanding, "the fixture run should leave a mandate for the human to close"

    capability_id = outstanding[0]
    control = next(
        c["offered_control_ids"][0]
        for c in zone["capabilities"]
        if c["capability_id"] == capability_id and c["offered_control_ids"]
    )
    baseline = sign(
        client,
        engine_run,
        choices=[
            *[
                choice
                for choice in closing_choices(engine_run)
                if not (
                    choice["zone_id"] == zone_id and choice["capability_id"] == capability_id
                )
            ],
            {
                "kind": "compensatory_declared",
                "zone_id": zone_id,
                "capability_id": capability_id,
                "control_id": control,
                "rationale": (
                    "El objetivo sigue en pie y el activo no admite el mecanismo: se declara "
                    "este control como compensatorio, con revisión trimestral."
                ),
            },
        ],
    )
    plan = ssp(client, baseline["baseline_id"])
    entry = next(
        e
        for e in by_components(plan)
        if _prop(e, "capability-outcome") == "compensated" and _zone_of(plan, e) == zone_id
    )

    assert entry["implementation-status"]["state"] == "alternative"
    assert "compensatorio" in entry["remarks"]


def test_a_gap_accepted_in_writing_is_flagged_rather_than_smoothed_over(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    """OSCAL has no state for it. The export says so instead of picking one quietly."""
    baseline = sign(client, engine_run)
    plan = ssp(client, baseline["baseline_id"])

    accepted = [e for e in by_components(plan) if _prop(e, "capability-outcome") == "accepted_gap"]
    assert accepted, "the fixture composition accepts every outstanding mandate as a gap"
    for entry in accepted:
        assert entry["implementation-status"]["state"] == "partial"
        assert "no define un estado" in entry["implementation-status"]["remarks"]
        assert _prop(entry, "gap-accepted") == "true"


def test_the_export_declares_itself_partial(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    baseline = sign(client, engine_run)
    metadata = ssp(client, baseline["baseline_id"])["metadata"]

    assert _prop(metadata, "export-kind") == "partial"
    assert "parcial" in metadata["remarks"]
    assert "no es una declaración de conformidad" in metadata["remarks"].lower()


def test_the_written_reasons_survive_the_translation(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    reason = "Sin mecanismo aplicable en la zona; el residual se asume con vigilancia reforzada."
    baseline = sign(client, engine_run, choices=closing_choices(engine_run, reason))
    plan = ssp(client, baseline["baseline_id"])

    accepted = [e for e in by_components(plan) if _prop(e, "capability-outcome") == "accepted_gap"]
    assert accepted
    assert all(reason in entry["remarks"] for entry in accepted)


def test_the_export_points_back_at_the_ledger(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    baseline = sign(client, engine_run)
    plan = ssp(client, baseline["baseline_id"])
    path = baseline["audit_log_path"]

    assert any(link["href"] == path for link in plan["metadata"]["links"])
    assert all(any(link["href"] == path for link in e["links"]) for e in by_components(plan))
    assert client.get(path).status_code == 200


# --- reproducibility -----------------------------------------------------------


def test_the_same_baseline_exports_to_the_same_ids(
    client: TestClient, engine_run: dict[str, Any]
) -> None:
    """Derived with uuid5 from what they name: reproducible, like everything else."""
    baseline = sign(client, engine_run)

    assert ssp(client, baseline["baseline_id"]) == ssp(client, baseline["baseline_id"])


def _prop(node: dict[str, Any], name: str) -> str | None:
    for prop in node.get("props", []):
        if prop["name"] == name:
            return str(prop["value"])
    return None


def _zone_of(plan: dict[str, Any], entry: dict[str, Any]) -> str | None:
    for component in plan["system-implementation"]["components"]:
        if component["uuid"] == entry["component-uuid"]:
            return _prop(component, "zone-id")
    return None
