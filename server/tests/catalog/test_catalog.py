"""UCM-7/UCM-43 - The v0.2.0 catalog loads, validates and meets its invariants."""

from collections import Counter

from app.catalog.loader import load_catalog
from app.catalog.schemas import ControlType, Framework, Jurisdiction, MappingType

CATALOG = load_catalog()

# Which jurisdiction each framework speaks from. A framework whose origin drifts
# between controls would make the regional delta meaningless: the lens filters on
# exactly this field.
JURISDICTION_OF = {
    Framework.CSF: Jurisdiction.US,
    Framework.CIS: Jurisdiction.US,
    Framework.IEC62443: Jurisdiction.INTL,
    Framework.NIS2: Jurisdiction.EU,
    Framework.IMO: Jurisdiction.INTL_MARITIME,
}


def test_version() -> None:
    assert CATALOG.catalog_version == "0.2.0"


def test_counts() -> None:
    # Frozen for v0.2.0 (regression). Update on every version bump.
    assert len(CATALOG.capabilities) == 37
    assert len(CATALOG.controls) == 225
    assert len(CATALOG.mappings) == 263


def test_counts_per_framework() -> None:
    # CSF 2.0 complete (the 106 subcategories of the Core) and IEC 62443-3-3
    # complete (the 51 SRs of the seven FRs): both are closed sets, and a count
    # that drifts off them means the seeding stopped being complete.
    assert Counter(c.framework for c in CATALOG.controls) == {
        Framework.CSF: 106,
        Framework.IEC62443: 51,
        Framework.CIS: 49,
        Framework.NIS2: 13,
        Framework.IMO: 6,
    }


def test_v0_1_0_ids_all_survive() -> None:
    """v0.2.0 is a strict superset: the rule files still name 41 of these controls."""
    previous = load_catalog("data/catalog/catalog.v0.1.0.json")

    assert previous.control_ids <= CATALOG.control_ids
    assert previous.capability_ids <= CATALOG.capability_ids


def test_no_orphans_and_no_unused() -> None:
    assert CATALOG.orphan_capabilities() == set()
    assert CATALOG.unused_controls() == set()


def test_referential_integrity() -> None:
    for m in CATALOG.mappings:
        assert m.capability_id in CATALOG.capability_ids
        assert m.control_id in CATALOG.control_ids


def test_coverage_weight_bounds() -> None:
    assert all(0.0 <= m.coverage_weight <= 1.0 for m in CATALOG.mappings)


def test_every_capability_is_offered_by_more_than_one_control() -> None:
    """Side-by-side composition is the contribution: one option is not a choice."""
    for capability in CATALOG.capabilities:
        offered = CATALOG.mappings_for(capability.id)
        assert len(offered) >= 2, f"{capability.id} offers a single option"


def test_a_framework_speaks_from_one_jurisdiction() -> None:
    for control in CATALOG.controls:
        assert control.jurisdiction is JURISDICTION_OF[control.framework], control.id


def test_official_ids_are_unique_within_their_framework() -> None:
    seen = Counter((c.framework, c.official_id) for c in CATALOG.controls)
    assert [pair for pair, n in seen.items() if n > 1] == []


def test_the_legal_overlay_is_never_a_mechanism() -> None:
    """NIS2 and IMO oblige; they do not implement. Their mappings stay contextual.

    The distinction is load-bearing twice over: a legal obligation is Tier 0
    whatever the SL-target says, and the regional delta reports *exigencia* added
    rather than coverage added. A legal control mapped as `total` would claim the
    law itself covers the capability.
    """
    overlay = {
        c.id for c in CATALOG.controls if c.framework in (Framework.NIS2, Framework.IMO)
    }
    for mapping in CATALOG.mappings:
        if mapping.control_id in overlay:
            assert mapping.mapping_type is MappingType.CONTEXTUAL, mapping.control_id
            assert mapping.coverage_weight <= 0.4, mapping.control_id


def test_only_a_binding_instrument_is_typed_legal() -> None:
    """`legal` makes a capability mandatory unconditionally, so guidance is not legal."""
    legal = {c.official_id for c in CATALOG.controls if c.control_type is ControlType.LEGAL}

    assert legal == {"Art. 20", "Art. 21", "Art. 23", "MSC.428(98)"} | {
        f"Art. 21(2)({letter})" for letter in "abcdefghij"
    }


def test_regional_delta_is_seeded() -> None:
    # The regional delta enters as contextual with EU jurisdiction (NIS2).
    eu_contextual = [
        m
        for m in CATALOG.mappings
        if m.mapping_type is MappingType.CONTEXTUAL and m.provenance.jurisdiction.value == "EU"
    ]
    assert eu_contextual, "there must be at least one contextual mapping with EU jurisdiction"
