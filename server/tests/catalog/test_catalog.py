"""The v0.6.0 catalog loads, validates and meets its invariants."""

from collections import Counter

import pytest

from app.catalog.loader import load_catalog
from app.catalog.schemas import (
    ControlType,
    Framework,
    Jurisdiction,
    MappingType,
    ProvenanceSource,
    Sector,
)

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
    # US legal corpus: CIRCIA transversal, TSA sectoral, both US.
    Framework.CIRCIA: Jurisdiction.US,
    Framework.TSA: Jurisdiction.US,
}


def test_version() -> None:
    assert CATALOG.catalog_version == "0.6.0"


def test_counts() -> None:
    # Frozen for v0.6.0 (regression). Update on every version bump. v0.6.0 adds
    # the US legal corpus, broken down obligation by obligation like NIS2's
    # Art. 21(2): CIRCIA contributes its four statutory duties and the TSA eight
    # (three for SD-01, five for SD-02), each its own control with one mapping — a
    # strict superset of v0.5.0.
    assert len(CATALOG.capabilities) == 37
    assert len(CATALOG.controls) == 238
    assert len(CATALOG.mappings) == 278


def test_counts_per_framework() -> None:
    # CSF 2.0 complete (the 106 subcategories of the Core) and IEC 62443-3-3
    # complete (the 51 SRs of the seven FRs): both are closed sets, and a count
    # that drifts off them means the seeding stopped being complete.
    assert Counter(c.framework for c in CATALOG.controls) == {
        Framework.CSF: 106,
        Framework.IEC62443: 51,
        Framework.CIS: 49,
        Framework.NIS2: 13,
        # Six functional elements since MSC-FAL.1/Circ.3/Rev.3 put Govern first,
        # plus the binding resolution MSC.428(98) itself.
        Framework.IMO: 7,
        # US legal corpus, one control per distinct obligation: CIRCIA's four
        # statutory duties (incident 72 h, ransom 24 h, supplemental, records
        # preservation) and the TSA's eight (SD-01: report, coordinator, assessment;
        # SD-02: segmentation, MFA, monitoring, patching, TSA-approved plan).
        Framework.CIRCIA: 4,
        Framework.TSA: 8,
    }


@pytest.mark.parametrize("version", ["0.1.0", "0.2.0", "0.3.0", "0.4.0", "0.5.0"])
def test_earlier_ids_all_survive(version: str) -> None:
    """Every version is a strict superset: the rule files still name these controls.

    Realigning the IMO to Rev.3 moved `official_id`s, not identities, so nothing
    a rule or a test cites can go missing by a catalog bump.
    """
    previous = load_catalog(f"data/catalog/catalog.v{version}.json")

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
    """NIS2, IMO and CIRCIA oblige; they do not implement. Their mappings stay contextual.

    The distinction is load-bearing twice over: a legal obligation is Tier 0
    whatever the SL-target says, and the regional delta reports *exigencia* added
    rather than coverage added. A legal control mapped as `total` would claim the
    law itself covers the capability.

    The TSA is deliberately excluded: SD-2021-02 is the one legal control that
    *does* prescribe a zone mechanism, and that exception is asserted on its own in
    `test_tsa_sd02_is_the_legal_obligation_that_prescribes_a_mechanism`.
    """
    overlay = {
        c.id
        for c in CATALOG.controls
        if c.framework in (Framework.NIS2, Framework.IMO, Framework.CIRCIA)
    }
    for mapping in CATALOG.mappings:
        if mapping.control_id in overlay:
            assert mapping.mapping_type is MappingType.CONTEXTUAL, mapping.control_id
            assert mapping.coverage_weight <= 0.4, mapping.control_id


def test_tsa_sd02_is_the_legal_obligation_that_prescribes_a_mechanism() -> None:
    """A sectoral regulator can legislate a concrete zone mechanism.

    Law usually binds only the organization. TSA SD-2021-02 is the exception — two
    of its duties prescribe OT/IT segmentation and MFA on access — so those mappings
    are `partial`/`compensatory`, not contextual, and move coverage. Its other
    duties, and every SD-2021-01 duty, stay contextual.
    """
    mechanism = {
        m.control_id: (m.capability_id, m.mapping_type)
        for m in CATALOG.mappings
        if m.mapping_type is not MappingType.CONTEXTUAL and m.control_id.startswith("CTL-TSA-")
    }
    assert mechanism["CTL-TSA-SD02-SEGMENT"] == ("CAP-PR-SEGMENT", MappingType.PARTIAL)
    assert mechanism["CTL-TSA-SD02-MFA"] == ("CAP-PR-MFA", MappingType.COMPENSATORY)

    # Every SD-01 duty (reporting, coordinator, assessment) is contextual.
    sd01 = [m for m in CATALOG.mappings if m.control_id.startswith("CTL-TSA-SD01-")]
    assert len(sd01) == 3
    assert all(m.mapping_type is MappingType.CONTEXTUAL for m in sd01)


def test_only_a_binding_instrument_is_typed_legal() -> None:
    """`legal` makes a capability mandatory unconditionally, so guidance is not legal."""
    legal = {c.official_id for c in CATALOG.controls if c.control_type is ControlType.LEGAL}

    assert legal == {"Art. 20", "Art. 21", "Art. 23", "MSC.428(98)"} | {
        f"Art. 21(2)({letter})" for letter in "abcdefghij"
    } | {
        # US legal corpus, one official id per distinct obligation.
        "CIRCIA 6 USC 681b(a)(1)",
        "CIRCIA 6 USC 681b(a)(2)",
        "CIRCIA 6 USC 681b(a)(3)",
        "CIRCIA 6 USC 681b(a)(4)",
        "SD Pipeline-2021-01G (report to CISA)",
        "SD Pipeline-2021-01G (cybersecurity coordinator)",
        "SD Pipeline-2021-01G (gap assessment)",
        "SD Pipeline-2021-02G (network segmentation)",
        "SD Pipeline-2021-02G (multi-factor authentication)",
        "SD Pipeline-2021-02G (continuous monitoring)",
        "SD Pipeline-2021-02G (risk-based patching)",
        "SD Pipeline-2021-02G (TSA-approved plan)",
    }


def test_only_the_legal_layer_declares_a_sector_scope() -> None:
    """Scope is declared by the legal layer, transversal for the rest.

    The IMO controls govern ships (the ISM Code), NIS2 governs the sectors of its
    Annexes and the TSA governs designated pipelines (transport); the technical
    frameworks are cross-sector by design and declare nothing. Empty scope is what
    keeps a catalog bump from silently narrowing what applies to an asset, and an
    enumerated list — however long — is never that.

    Being legal is necessary but not sufficient for a declared scope: CIRCIA is a
    legal obligation and yet transversal (the 16 US critical-infrastructure
    sectors), so it declares no scope. What the invariant pins is the converse —
    every *scoped* control is a legal one.
    """
    scoped = {c.id for c in CATALOG.controls if not c.transversal}
    sectoral_legal = {
        c.id
        for c in CATALOG.controls
        if c.framework in (Framework.IMO, Framework.NIS2, Framework.TSA)
    }

    assert scoped == sectoral_legal
    for control in CATALOG.controls:
        if control.framework is Framework.IMO:
            # IMO governs shipping alone.
            assert control.applies_to_sectors == [Sector.MARITIME], control.id
        if control.framework is Framework.NIS2:
            # NIS2 is multisector: an enumerated list, not transversal.
            assert not control.transversal, control.id
            assert len(control.applies_to_sectors) > 1, control.id
            assert Sector.ENERGY in control.applies_to_sectors, control.id
        if control.framework is Framework.TSA:
            # The TSA governs the Transportation Systems Sector: 'transport', not
            # 'energy' — the US/EU misalignment the delta makes demonstrable.
            assert control.applies_to_sectors == [Sector.TRANSPORT], control.id
        if control.framework is Framework.CIRCIA:
            # Transversal: a legal obligation that declares no sector scope.
            assert control.transversal, control.id


def test_regional_delta_is_seeded() -> None:
    # The regional delta enters as contextual with EU jurisdiction (NIS2).
    eu_contextual = [
        m
        for m in CATALOG.mappings
        if m.mapping_type is MappingType.CONTEXTUAL and m.provenance.jurisdiction.value == "EU"
    ]
    assert eu_contextual, "there must be at least one contextual mapping with EU jurisdiction"


# --- What may call itself an official crosswalk -----------------------------


def test_only_csf_and_cis_may_claim_an_official_crosswalk() -> None:
    """No published crosswalk reaches IEC 62443, NIS2 or the IMO circular.

    The equivalences into those three are the author's, and saying otherwise
    would borrow authority the catalog does not have.
    """
    claimed = {
        control.framework
        for control in CATALOG.controls
        for mapping in CATALOG.mappings
        if mapping.control_id == control.id
        and mapping.provenance.source is ProvenanceSource.OFFICIAL_CROSSWALK
    }

    assert claimed <= {Framework.CSF, Framework.CIS}


def test_the_official_crosswalk_claims_stay_where_they_were_verified() -> None:
    """Frozen after checking all 121 v0.2.0 claims against NIST's own references.

    Ten CIS claims and two CSF ones were not backed — seven of the CIS safeguards
    are not referenced by the CSF 2.0 crosswalk at all — and are now declared
    `author_judgment`. The count is pinned because the failure mode is silent: a
    later edit can re-mark a mapping as official and nothing else would notice.
    Raising these numbers is legitimate only with a source that backs them.
    """
    official = Counter(
        control.framework
        for control in CATALOG.controls
        for mapping in CATALOG.mappings
        if mapping.control_id == control.id
        and mapping.provenance.source is ProvenanceSource.OFFICIAL_CROSSWALK
    )

    assert official == {Framework.CSF: 100, Framework.CIS: 9}


def test_every_downgraded_mapping_says_why() -> None:
    """A mapping that stopped claiming a crosswalk has to carry the reason it stopped.

    Two reasons, and the note distinguishes them because they are different
    admissions: NIST's references do not reach the safeguard at all, or they
    reach it from a category other than the capability's seed.
    """
    unreferenced = [m for m in CATALOG.mappings if "no referencia" in m.provenance.note]
    other_category = [m for m in CATALOG.mappings if "desde otra categoría" in m.provenance.note]
    wrong_seed = [m for m in CATALOG.mappings if "categoría semilla" in m.provenance.note]

    assert (len(unreferenced), len(other_category), len(wrong_seed)) == (7, 3, 2)
    for mapping in (*unreferenced, *other_category, *wrong_seed):
        assert mapping.provenance.source is ProvenanceSource.AUTHOR_JUDGMENT, mapping.control_id
        assert "juicio de autor" in mapping.provenance.note, mapping.control_id
