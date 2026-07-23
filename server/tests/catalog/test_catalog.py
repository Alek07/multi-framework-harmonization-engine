"""UCM-7 - The v0.1.0 catalog loads, validates and meets its invariants."""

from app.catalog.loader import load_catalog
from app.catalog.schemas import MappingType

CATALOG = load_catalog()


def test_version() -> None:
    assert CATALOG.catalog_version == "0.1.0"


def test_counts() -> None:
    # Frozen for v0.1.0 (regression). Update on every version bump.
    assert len(CATALOG.capabilities) == 24
    assert len(CATALOG.controls) == 69
    assert len(CATALOG.mappings) == 77


def test_no_orphans_and_no_unused() -> None:
    assert CATALOG.orphan_capabilities() == set()
    assert CATALOG.unused_controls() == set()


def test_referential_integrity() -> None:
    for m in CATALOG.mappings:
        assert m.capability_id in CATALOG.capability_ids
        assert m.control_id in CATALOG.control_ids


def test_coverage_weight_bounds() -> None:
    assert all(0.0 <= m.coverage_weight <= 1.0 for m in CATALOG.mappings)


def test_regional_delta_is_seeded() -> None:
    # The regional delta enters as contextual with EU jurisdiction (NIS2).
    eu_contextual = [
        m
        for m in CATALOG.mappings
        if m.mapping_type is MappingType.CONTEXTUAL and m.provenance.jurisdiction.value == "EU"
    ]
    assert eu_contextual, "there must be at least one contextual mapping with EU jurisdiction"
