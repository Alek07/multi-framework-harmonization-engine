"""UCM-9 - Step 3: the three gating outcomes and the golden rule that bounds them.

Gating removes *mechanisms*, never required *capabilities*, and never silently:
every exclusion carries its rule, the premises read from the profile and a
written justification, and whatever is left short becomes an explicit gap.
"""

from app.assets.schemas import AssetProfile
from app.catalog.schemas import Catalog
from app.engine.schemas import (
    CapabilityStatus,
    GatingOutcome,
    ProfileGating,
    ProfileResolution,
)
from app.engine.service import gate_profile
from tests.engine.conftest import ZONE_ENG, ZONE_OT, ZONE_SIS

DATACONF = "CAP-PR-DATACONF"
MALWARE = "CAP-PR-MALWARE"
MEDIA = "CAP-PR-MEDIA"
MFA = "CAP-PR-MFA"
PATCH = "CAP-PR-PATCH"
REPORT = "CAP-RS-REPORT"
IR = "CAP-RS-IR"

CIS_ANTIMALWARE = "CTL-CIS-1001"
CIS_AUTORUN = "CTL-CIS-1003"
CIS_MFA_ADMIN = "CTL-CIS-0605"
CIS_DATA_AT_REST = "CTL-CIS-0311"
CSF_ALLOWLIST = "CTL-CSF-PRPS05"


# --- "No aplica": a justified exclusion is a deliverable, not a gap -----------


def test_not_applicable_excludes_the_mechanism_without_opening_a_gap(
    gating_a: ProfileGating,
) -> None:
    dataconf = gating_a.zone(ZONE_OT).capability(DATACONF)
    excluded = next(d for d in dataconf.excluded if d.control_id == CIS_DATA_AT_REST)

    assert excluded.outcome is GatingOutcome.NOT_APPLICABLE
    assert excluded.rule_id == "GATE-NA-DATA-AT-REST-EMBEDDED"
    # The premise the engine read from the profile, not a hunch — and stated as a
    # sentence the operator can judge, not as the field path it came from.
    assert "la zona no tiene sistema operativo de propósito general" in excluded.evidence
    # The capability keeps a full mechanism: the exclusion costs nothing.
    assert dataconf.status is CapabilityStatus.COVERED_BY_MECHANISM
    assert dataconf.coverage == dataconf.coverage_before_gating == 1.0
    assert dataconf.gap is None


def test_justified_exclusions_are_a_deliverable_of_the_zone(gating_a: ProfileGating) -> None:
    """Frozen on purpose: the excluded list is what the operator signs, not a side effect.

    Two kinds of `no aplica` sit here together: the technical ones a rule fires on
    the embedded controller, and the sectoral ones (UCM-47) — the seven IMO
    controls govern ships, not an onshore gas pipeline, so they are excluded by
    scope. Both are deliverables, not gaps.
    """
    exclusions = gating_a.zone(ZONE_OT).justified_exclusions
    assert {d.control_id for d in exclusions} == {
        CIS_ANTIMALWARE,
        CIS_AUTORUN,
        CIS_DATA_AT_REST,
        "CTL-CIS-0403",
        "CTL-CIS-0506",
        "CTL-CIS-0603",
        "CTL-CIS-0607",
        "CTL-CIS-0608",
        "CTL-CIS-1007",
        "CTL-CIS-1102",
        "CTL-CIS-1207",
        "CTL-IEC-SR110",
        "CTL-IEC-SR112",
        "CTL-IEC-SR27",
        "CTL-IEC-SR53",
        # Sectoral exclusions: the maritime norm does not govern this pipeline.
        "CTL-IMO-42898",
        "CTL-IMO-FAL3GOV",
        "CTL-IMO-FAL3ID",
        "CTL-IMO-FAL3PR",
        "CTL-IMO-FAL3DE",
        "CTL-IMO-FAL3RS",
        "CTL-IMO-FAL3RC",
    }
    assert all(d.rationale.strip() and d.evidence for d in exclusions)


# --- "Objetivo sin mecanismo": the objective survives the mechanism -----------


def test_an_orphaned_objective_owes_a_compensatory_control(gating_a: ProfileGating) -> None:
    mfa = gating_a.zone(ZONE_OT).capability(MFA)
    admin_mfa = next(d for d in mfa.excluded if d.control_id == CIS_MFA_ADMIN)

    assert admin_mfa.outcome is GatingOutcome.OBJECTIVE_WITHOUT_MECHANISM
    assert admin_mfa.compensation  # the rule names what has to cover the outcome instead
    assert mfa.required is True


def test_gating_reveals_the_coverage_it_costs_instead_of_hiding_it(
    gating_a: ProfileGating,
) -> None:
    mfa = gating_a.zone(ZONE_OT).capability(MFA)
    # The only total mechanism (CIS 6.5) cannot live on an embedded controller:
    # what remains are partial pieces, and the engine says so.
    assert mfa.coverage_before_gating == 0.9
    assert mfa.coverage == 0.6
    assert mfa.gap is not None
    assert mfa.gap.kind.value == "partial_only"
    assert mfa.gap.residual == 0.4


def test_a_capability_left_without_a_direct_mechanism_falls_back_to_compensation(
    gating_a: ProfileGating,
) -> None:
    """The crown jewel is where this happens, and only there.

    In the corridor the OT mechanism survives — autorun/autoplay is an OS feature
    the controller does not have, but SR 2.3 still governs portable devices. The
    SIS accepts no portable media at all, so the capability is left with nothing
    direct and falls back to the compensatory mapping. Same catalog, same
    profile, different zone: that difference is the point of gating.
    """
    corridor = gating_a.zone(ZONE_OT).capability(MEDIA)
    assert corridor.status is CapabilityStatus.COVERED_BY_MECHANISM
    assert corridor.retained_control_ids == ["CTL-IEC-SR23"]

    media = gating_a.zone(ZONE_SIS).capability(MEDIA)
    assert media.status is CapabilityStatus.COMPENSATORY_REQUIRED
    assert media.retained_control_ids == []
    assert media.compensatory_control_ids == [CSF_ALLOWLIST]
    assert media.coverage_before_gating == 0.9
    assert media.coverage == 0.4
    assert media.gap is not None


def test_an_excluded_mechanism_does_not_drag_the_capability_down_with_it(
    gating_a: ProfileGating,
) -> None:
    patch = gating_a.zone(ZONE_OT).capability(PATCH)
    orphaned = next(d for d in patch.excluded if d.control_id == "CTL-CIS-0701")
    assert orphaned.outcome is GatingOutcome.OBJECTIVE_WITHOUT_MECHANISM
    # The IT remediation cadence goes; the capability keeps other mechanisms.
    assert patch.status is CapabilityStatus.COVERED_BY_MECHANISM
    assert patch.coverage == 1.0


# --- "Ámbito equivocado": deferred, not deleted -------------------------------


def test_wrong_scope_defers_the_capability_to_the_organizational_layer(
    gating_a: ProfileGating,
) -> None:
    report = gating_a.zone(ZONE_OT).capability(REPORT)
    assert report.status is CapabilityStatus.DEFERRED_TO_ORGANIZATIONAL_LAYER
    assert report.required is True
    assert report.deferred_to  # the layer that goes on answering for it is named
    # The organizational overlay is deferred with a named layer; the maritime
    # obligation is not deferred at all — it does not govern this sector (UCM-47).
    deferred = [d for d in report.excluded if d.outcome is GatingOutcome.WRONG_SCOPE]
    assert deferred
    assert all(d.deferred_to for d in deferred)
    imo = next(d for d in report.excluded if d.control_id == "CTL-IMO-42898")
    assert imo.outcome is GatingOutcome.NOT_APPLICABLE


def test_a_legal_obligation_is_never_a_mechanism(gating_a: ProfileGating) -> None:
    """A legal obligation obliges the operator; it is never a zone mechanism.

    NIS2 governs this asset (it is transversal), so it is deferred to the
    organizational layer. IMO governs ships, not an onshore pipeline: it is not
    deferred but excluded by sector (UCM-47) — offering it would assert a maritime
    obligation the pipeline does not have.
    """
    deferrals = {d.control_id for d in gating_a.zone(ZONE_OT).organizational_deferrals}
    assert {"CTL-NIS2-A20", "CTL-NIS2-A21", "CTL-NIS2-A23"} <= deferrals
    assert "CTL-IMO-42898" not in deferrals

    not_applicable = {d.control_id for d in gating_a.zone(ZONE_OT).justified_exclusions}
    assert "CTL-IMO-42898" in not_applicable


def test_a_partial_deferral_leaves_the_capability_in_the_asset(
    gating_a: ProfileGating,
) -> None:
    incident = gating_a.zone(ZONE_OT).capability(IR)
    # Designating responders, keeping the process and escalating are organizational;
    # executing the plan on the asset, triaging and categorising are not.
    deferred = [d for d in incident.excluded if d.outcome is GatingOutcome.WRONG_SCOPE]
    assert {d.control_id for d in deferred} == {
        "CTL-CIS-1701",
        "CTL-CIS-1704",
        "CTL-CSF-GVSC08",
        "CTL-CSF-IDIM04",
        "CTL-CSF-RSMA04",
        "CTL-NIS2-A21B",
    }
    # The maritime functional element (FAL3 Respond) is out of sector, not deferred.
    maritime = next(d for d in incident.excluded if d.control_id == "CTL-IMO-FAL3RS")
    assert maritime.outcome is GatingOutcome.NOT_APPLICABLE
    assert incident.status is CapabilityStatus.COVERED_BY_MECHANISM
    assert incident.retained_control_ids == [
        "CTL-CSF-RSMA01",
        "CTL-CSF-RSMA02",
        "CTL-CSF-RSMA03",
        "CTL-CSF-RSMA05",
    ]


# --- The golden rule ---------------------------------------------------------


def test_gating_never_removes_a_required_capability(
    gating_a: ProfileGating, gating_b: ProfileGating, catalog: Catalog
) -> None:
    for gating in (gating_a, gating_b):
        for zone in gating.zones:
            assert len(zone.capabilities) == len(catalog.capabilities)
            assert all(c.required is True for c in zone.capabilities)


def test_gating_never_acts_in_silence(gating_a: ProfileGating, gating_b: ProfileGating) -> None:
    for gating in (gating_a, gating_b):
        for zone in gating.zones:
            for capability in zone.capabilities:
                assert capability.rationale.strip(), capability.capability_id
                for decision in capability.excluded:
                    assert decision.rule_id and decision.rationale.strip()
                    assert decision.evidence, decision.control_id
                if capability.status is CapabilityStatus.COMPENSATORY_REQUIRED:
                    assert capability.gap is not None
                if capability.status is CapabilityStatus.DEFERRED_TO_ORGANIZATIONAL_LAYER:
                    assert capability.deferred_to


def test_an_excluded_mechanism_stays_visible_in_the_resolution(
    gating_a: ProfileGating, resolution_a: ProfileResolution
) -> None:
    """Gating decorates the candidates; it never deletes one from the table."""
    for zone in gating_a.zones:
        offered = {
            o.control_id
            for capability in resolution_a.zone(zone.zone.zone_id).capabilities
            for o in capability.options
        }
        assert {d.control_id for d in zone.decisions} <= offered


def test_gating_never_widens_coverage(gating_a: ProfileGating, gating_b: ProfileGating) -> None:
    for gating in (gating_a, gating_b):
        for zone in gating.zones:
            for capability in zone.capabilities:
                assert capability.coverage <= capability.coverage_before_gating


# --- Same catalog, different zone, different baseline ------------------------


def test_the_same_catalog_gates_differently_in_each_zone(
    gating_a: ProfileGating, gating_b: ProfileGating
) -> None:
    ot = {d.control_id for d in gating_a.zone(ZONE_OT).decisions}
    hybrid = {d.control_id for d in gating_b.zone(ZONE_ENG).decisions}
    assert hybrid < ot  # the embedded controller rules out strictly more mechanisms

    # The engineering workstation is a general-purpose host: the very mechanisms
    # the controller cannot take are the ones it keeps.
    for control_id in (CIS_ANTIMALWARE, CIS_AUTORUN, CIS_MFA_ADMIN, CIS_DATA_AT_REST):
        assert control_id in ot
        assert control_id not in hybrid


def test_the_technical_gating_is_what_separates_the_two_profiles(
    gating_a: ProfileGating, gating_b: ProfileGating
) -> None:
    hybrid = gating_b.zone(ZONE_ENG)
    # The general-purpose host triggers no *technical* `no aplica`. The sectoral
    # exclusions (UCM-47) are common to both profiles — both are energy — so they
    # do not separate the two; the technical gating is what does.
    technical_na = [
        d for d in hybrid.justified_exclusions if d.rule_id != "APPLIC-SECTOR"
    ]
    assert technical_na == []
    assert hybrid.compensatory_requirements == []
    # Both profiles defer the same organizational layer: scope does not depend on the zone.
    assert {d.control_id for d in hybrid.organizational_deferrals} == {
        d.control_id for d in gating_a.zone(ZONE_OT).organizational_deferrals
    }
    assert gating_a.zone(ZONE_OT).justified_exclusions
    assert gating_a.zone(ZONE_OT).compensatory_requirements


def test_one_hybrid_asset_gates_its_own_zones_off_different_premises() -> None:
    """The premises are the zone's, not the asset's — the reason `nature` lives on `Zone`.

    A single asset holding an embedded safety controller *and* a Windows operator
    station settles `general_purpose_os` twice, differently. While the flag was
    asset-wide one of the two zones had to be gated on the other's premises: the
    controller kept an antimalware agent it cannot host, or the workstation lost
    one it can. Here the same catalog, the same rules and the same asset produce
    the exclusion in one zone and not in the other.
    """
    embedded = {
        "general_purpose_os": False,
        "networked": True,
        "hybrid_it_ot": False,
        "interactive_users": False,
        "office_it_surface": False,
    }
    workstation = {**embedded, "general_purpose_os": True, "interactive_users": True}
    profile = AssetProfile.model_validate(
        {
            "id": "PROFILE-HYBRID",
            "name": "Asset with one embedded zone and one general-purpose zone",
            "case": "HYBRID_IT_OT",
            "zones": [
                {"id": "Z-EMBEDDED", "purdue": "L1", "target_sl": 3, "nature": embedded},
                {"id": "Z-WORKSTATION", "purdue": "L3", "target_sl": 3, "nature": workstation},
            ],
            "conduits": [],
            "criticality": {
                "physical_consequence": "overpressure_rupture_leak",
                "scale": "catastrophic",
                "threat_model": "ATTACK_for_ICS",
            },
        }
    )

    gating = gate_profile(profile)
    controller = gating.zone("Z-EMBEDDED").capability(MALWARE)
    station = gating.zone("Z-WORKSTATION").capability(MALWARE)

    excluded = next(d for d in controller.excluded if d.control_id == CIS_ANTIMALWARE)
    assert excluded.outcome is GatingOutcome.NOT_APPLICABLE
    assert "la zona no tiene sistema operativo de propósito general" in excluded.evidence
    assert CIS_ANTIMALWARE not in [d.control_id for d in station.excluded]

    # And the requirement survives the exclusion in both: gating removes
    # mechanisms, never capabilities.
    assert controller.required is station.required is True


def test_both_zones_of_the_ot_profile_are_gated(gating_a: ProfileGating) -> None:
    assert [z.zone.zone_id for z in gating_a.zones] == [ZONE_OT, ZONE_SIS]
    assert gating_a.zone(ZONE_SIS).decisions


def test_gating_reports_the_versions_it_ran_with(gating_a: ProfileGating) -> None:
    assert gating_a.catalog_version == "0.4.0"
    assert gating_a.rules_version == "0.1.0"
    assert gating_a.gating_version == "0.2.0"
