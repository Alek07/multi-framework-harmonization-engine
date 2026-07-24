"""UCM-8 - Step 1: every capability, every candidate, nothing dropped."""

from app.catalog.schemas import (
    Capability,
    Catalog,
    Framework,
    FrameworkControl,
    Jurisdiction,
    Mapping,
    MappingType,
    Provenance,
    ProvenanceSource,
)
from app.engine.mapping import MAPPING_TYPE_RANK, build_options, map_zone
from app.engine.rules import RuleSet
from app.engine.schemas import ProfileResolution, ZoneContext, ZoneDomain
from tests.engine.conftest import ZONE_OT

OT_CONTEXT = ZoneContext(
    zone_id=ZONE_OT,
    domain=ZoneDomain.OT,
    target_sl=3,
    safety_relevant=True,
    derivation="fixture",
)


def test_every_capability_is_carried_into_every_zone(
    resolution_a: ProfileResolution, catalog: Catalog
) -> None:
    for zone in resolution_a.zones:
        assert [c.capability.id for c in zone.capabilities] == sorted(catalog.capability_ids)


def test_no_mapping_is_dropped(resolution_a: ProfileResolution, catalog: Catalog) -> None:
    # The invariant in its rawest form: candidates in == candidates out.
    for zone in resolution_a.zones:
        for resolution in zone.capabilities:
            expected = {m.control_id for m in catalog.mappings_for(resolution.capability.id)}
            assert {o.control_id for o in resolution.options} == expected


def test_options_are_ordered_by_breadth_then_weight(catalog: Catalog, rules: RuleSet) -> None:
    for capability, options in map_zone(catalog, rules, OT_CONTEXT):
        keys = [(MAPPING_TYPE_RANK[o.mapping_type], -o.coverage_weight) for o in options]
        assert keys == sorted(keys), f"unstable order for {capability.id}"


def test_a_capability_without_candidates_is_not_swallowed(rules: RuleSet) -> None:
    orphan = Capability(
        id="CAP-TEST-ORPHAN",
        name="Capacidad sin control",
        description="Capacidad exigida que ningún control del catálogo cubre.",
        csf_seed_category="PR.XX",
    )
    control = FrameworkControl(
        id="CTL-TEST-01",
        framework=Framework.CSF,
        official_id="PR.XX-01",
        title="Test control",
        paraphrased_description="Control de prueba.",
        jurisdiction=Jurisdiction.US,
        strength="resultado",
        type="technical",
    )
    covered = orphan.model_copy(update={"id": "CAP-TEST-COVERED"})
    catalog = Catalog(
        catalog_version="test",
        capabilities=[orphan, covered],
        controls=[control],
        mappings=[
            Mapping(
                capability_id=covered.id,
                control_id=control.id,
                type=MappingType.TOTAL,
                coverage_weight=1.0,
                provenance=Provenance(
                    source=ProvenanceSource.AUTHOR_JUDGMENT, jurisdiction=Jurisdiction.US
                ),
            )
        ],
    )

    assert build_options(catalog, orphan.id, rules, OT_CONTEXT) == []
    assert [c.id for c, _ in map_zone(catalog, rules, OT_CONTEXT)] == [covered.id, orphan.id]
