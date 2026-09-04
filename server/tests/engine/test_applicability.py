"""Sectoral applicability: a norm outside its sector is excluded, not offered.

A zone whose effective sectors do not meet a control's declared scope becomes a
justified `NOT_APPLICABLE` exclusion, with its rule, premise and reason — never a
silent drop. The match is set intersection: a norm applies when any one sector
coincides. IMO governs one sector; NIS2 enumerates many; the technical frameworks
declare none and are transversal.
"""

from __future__ import annotations

from app.assets.schemas import AssetProfile
from app.catalog.schemas import Catalog, FrameworkControl, Sector
from app.engine.applicability import (
    SECTOR_APPLICABILITY_RULE_ID,
    applicability_decision,
    control_applies,
)
from app.engine.schemas import (
    GatingOutcome,
    MandateSource,
    ProfileGating,
    ProfilePrioritization,
)
from app.engine.service import gate_profile, prioritize_profile
from app.engine.zones import zone_context
from tests.engine.conftest import ZONE_OT

IMO_RESOLUTION = "CTL-IMO-42898"
IMO_FUNCTIONAL = "CTL-IMO-FAL3RS"
IMO_CONTROLS = {
    "CTL-IMO-42898",
    "CTL-IMO-FAL3GOV",
    "CTL-IMO-FAL3ID",
    "CTL-IMO-FAL3PR",
    "CTL-IMO-FAL3DE",
    "CTL-IMO-FAL3RS",
    "CTL-IMO-FAL3RC",
}
NIS2_REPORT = "CTL-NIS2-A23"
REPORT = "CAP-RS-REPORT"


def control(catalog: Catalog, control_id: str) -> FrameworkControl:
    return next(c for c in catalog.controls if c.id == control_id)


# --- the predicate ------------------------------------------------------------


def test_a_transversal_control_applies_to_every_sector(catalog: Catalog) -> None:
    """Empty scope is the majority: a technical control is cross-sector by design."""
    cis = control(catalog, "CTL-CIS-1001")
    assert cis.transversal
    for sector in Sector:
        assert control_applies(cis, [sector])
    assert control_applies(cis, [])


def test_an_enumerated_scope_is_not_transversal(catalog: Catalog) -> None:
    """A list of many sectors is a positive claim, not "applies everywhere"."""
    nis2 = control(catalog, NIS2_REPORT)
    assert not nis2.transversal
    assert len(nis2.applies_to_sectors) > 1


def test_a_scoped_control_matches_by_intersection(catalog: Catalog) -> None:
    imo = control(catalog, IMO_RESOLUTION)
    assert imo.applies_to_sectors == [Sector.MARITIME]
    assert control_applies(imo, [Sector.MARITIME])
    assert control_applies(imo, [Sector.ENERGY, Sector.MARITIME])  # one match is enough
    assert not control_applies(imo, [Sector.ENERGY])
    assert not control_applies(imo, [Sector.ENERGY, Sector.WATER])


def test_a_multisector_norm_applies_on_any_matching_sector(catalog: Catalog) -> None:
    nis2 = control(catalog, NIS2_REPORT)
    assert control_applies(nis2, [Sector.ENERGY])
    assert control_applies(nis2, [Sector.WATER])
    assert control_applies(nis2, [Sector.MARITIME])


def test_undeclared_sectors_exclude_nothing(catalog: Catalog) -> None:
    """The safe reading: with no sector the engine cannot assert a norm is out of scope."""
    imo = control(catalog, IMO_RESOLUTION)
    assert control_applies(imo, [])


def test_the_decision_carries_its_rule_premise_and_reason(
    profile_a: AssetProfile, catalog: Catalog
) -> None:
    zone = zone_context(profile_a.zones[0], profile_a)  # PROFILE-A is energy
    decision = applicability_decision(control(catalog, IMO_RESOLUTION), REPORT, zone)

    assert decision is not None
    assert decision.outcome is GatingOutcome.NOT_APPLICABLE
    assert decision.rule_id == SECTOR_APPLICABILITY_RULE_ID
    assert any("sector" in premise for premise in decision.evidence)
    assert "no aplica" in decision.rationale
    assert "marítimo" in decision.rationale


def test_an_applicable_norm_yields_no_decision(
    profile_a: AssetProfile, catalog: Catalog
) -> None:
    maritime = profile_a.model_copy(update={"sectors": [Sector.MARITIME]})
    zone = zone_context(maritime.zones[0], maritime)
    assert applicability_decision(control(catalog, IMO_RESOLUTION), REPORT, zone) is None
    # And the multisector norm still applies here — maritime is one of its sectors.
    assert applicability_decision(control(catalog, NIS2_REPORT), REPORT, zone) is None


# --- through gating -----------------------------------------------------------


def gate(profile: AssetProfile, sectors: list[Sector]) -> ProfileGating:
    return gate_profile(profile.model_copy(update={"sectors": sectors}))


def test_imo_is_excluded_by_sector_for_an_energy_asset(gating_a: ProfileGating) -> None:
    """The pipeline is energy: the seven maritime controls are `no aplica`, not offered."""
    excluded = {
        d.control_id: d
        for d in gating_a.zone(ZONE_OT).decisions
        if d.control_id in IMO_CONTROLS
    }

    assert set(excluded) == IMO_CONTROLS
    assert all(d.outcome is GatingOutcome.NOT_APPLICABLE for d in excluded.values())
    # The resolution is also a legal obligation, so the legal-scope rule matched
    # too — kept as context, never lost, but applicability decides.
    assert "GATE-SCOPE-LEGAL-OBLIGATION" in excluded[IMO_RESOLUTION].also_matched_rule_ids
    # A functional element no rule targets: applicability alone excludes it.
    assert excluded[IMO_FUNCTIONAL].also_matched_rule_ids == []


def test_the_multisector_norm_is_not_excluded_from_the_energy_asset(
    gating_a: ProfileGating,
) -> None:
    """NIS2 enumerates energy among its sectors, so it applies — never sector-excluded."""
    sectoral = {
        d.control_id
        for d in gating_a.zone(ZONE_OT).decisions
        if d.rule_id == SECTOR_APPLICABILITY_RULE_ID
    }
    assert NIS2_REPORT not in sectoral
    assert not any(cid.startswith("CTL-NIS2") for cid in sectoral)


def test_a_maritime_berth_zone_keeps_the_maritime_norm(profile_a: AssetProfile) -> None:
    """The ACP case: one energy asset with a maritime berth zone.

    The corridor excludes IMO by sector; the berth, declaring `sectors=[maritime]`,
    keeps it. Same asset, same catalog, different zone.
    """
    berth = profile_a.zones[0].model_copy(
        update={"id": "Z-BERTH", "sectors": [Sector.MARITIME]}
    )
    hybrid = profile_a.model_copy(
        update={"sectors": [Sector.ENERGY], "zones": [profile_a.zones[0], berth]}
    )
    gating = gate_profile(hybrid)

    corridor_imo = next(
        d for d in gating.zone(ZONE_OT).decisions if d.control_id == IMO_RESOLUTION
    )
    assert corridor_imo.outcome is GatingOutcome.NOT_APPLICABLE

    berth_decisions = {d.control_id: d for d in gating.zone("Z-BERTH").decisions}
    # In the berth IMO is in sector, so it is not excluded by APPLIC-SECTOR; the
    # legal-obligation rule defers 42898 to the org layer instead.
    assert berth_decisions[IMO_RESOLUTION].outcome is GatingOutcome.WRONG_SCOPE
    assert IMO_FUNCTIONAL not in berth_decisions


def test_undeclared_sectors_offer_the_norm(profile_a: AssetProfile) -> None:
    """No sector declared: nothing is excluded on a premise nobody stated (invariant 2)."""
    gating = gate(profile_a, [])
    decisions = {d.control_id: d for d in gating.zone(ZONE_OT).decisions}

    assert decisions[IMO_RESOLUTION].outcome is GatingOutcome.WRONG_SCOPE
    assert not any(
        d.rule_id == SECTOR_APPLICABILITY_RULE_ID for d in gating.zone(ZONE_OT).decisions
    )


# --- through prioritisation ---------------------------------------------------


def priorities(profile: AssetProfile, sectors: list[Sector]) -> ProfilePrioritization:
    return prioritize_profile(profile.model_copy(update={"sectors": sectors}))


def test_an_out_of_sector_norm_creates_no_legal_mandate(profile_a: AssetProfile) -> None:
    """A pipeline owes no maritime law.

    Forcing the asset to 'energy' alone is the non-transport case: the TSA
    (transport) creates no mandate, while CIRCIA (transversal) still does — the US
    legal reading degrades gracefully rather than collapsing to nothing.
    """
    energy = priorities(profile_a, [Sector.ENERGY]).zone(ZONE_OT).capability(REPORT)
    legal = [m for m in energy.mandates if m.source is MandateSource.LEGAL_OBLIGATION]
    control_ids = {m.control_id for m in legal}

    assert IMO_RESOLUTION not in control_ids
    # Out of sector: every TSA duty is transport, not energy.
    assert not any(cid.startswith("CTL-TSA-") for cid in control_ids)
    # Transversal: CIRCIA's reporting duties apply to any critical asset.
    assert "CTL-CIRCIA-INCIDENT" in control_ids
    assert "CTL-CIRCIA-RANSOM" in control_ids
    # NIS2 (EU, multisector incl. energy) and CIRCIA (US, transversal) both stand.
    assert {m.jurisdiction.value for m in legal} == {"EU", "US"}


def test_the_maritime_norm_is_a_mandate_for_a_ship(profile_a: AssetProfile) -> None:
    maritime = priorities(profile_a, [Sector.MARITIME]).zone(ZONE_OT).capability(REPORT)
    legal = [m for m in maritime.mandates if m.source is MandateSource.LEGAL_OBLIGATION]

    assert any(m.control_id == IMO_RESOLUTION for m in legal)
