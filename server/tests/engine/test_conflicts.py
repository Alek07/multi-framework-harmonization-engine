"""UCM-8 - Step 2: the three conflict situations, and what the engine must not decide."""

from app.engine.schemas import (
    CandidateStatus,
    CapabilityResolution,
    ConflictType,
    GapKind,
    ProfileResolution,
    ResolutionMethod,
)
from tests.engine.conftest import ZONE_ENG, ZONE_OT, ZONE_SIS

MALWARE = "CAP-PR-MALWARE"
MFA = "CAP-PR-MFA"
IDENTITY = "CAP-PR-IDENTITY"
REPORT = "CAP-RS-REPORT"

IEC_MALWARE = "CTL-IEC-SR32"
CIS_MALWARE = "CTL-CIS-1001"


def _capability(resolution: ProfileResolution, zone_id: str, cap_id: str) -> CapabilityResolution:
    return next(c for c in resolution.zone(zone_id).capabilities if c.capability.id == cap_id)


# --- Overlap -----------------------------------------------------------------


def test_overlap_collapses_into_one_capability_with_side_by_side_options(
    resolution_a: ProfileResolution,
) -> None:
    identity = _capability(resolution_a, ZONE_OT, IDENTITY)
    overlaps = [c for c in identity.conflicts if c.conflict_type is ConflictType.OVERLAP]
    assert len(overlaps) == 1

    overlap = overlaps[0]
    assert overlap.method is ResolutionMethod.COLLAPSED
    # CSF PR.AA-01 and IEC SR 1.1 both cover the outcome in full: two options, one requirement.
    assert {"CTL-CSF-PRAA01", "CTL-IEC-SR11"} <= set(overlap.control_ids)
    assert overlap.superseded_control_ids == []
    assert overlap.requires_human_decision is False
    assert set(overlap.prevailing_control_ids) == set(overlap.control_ids)


# --- Granularity (1:N) -------------------------------------------------------


def test_granularity_reports_weights_and_never_sums_them(
    resolution_a: ProfileResolution,
) -> None:
    mfa = _capability(resolution_a, ZONE_OT, MFA)
    granularity = [c for c in mfa.conflicts if c.conflict_type is ConflictType.GRANULARITY]
    assert len(granularity) == 1
    assert granularity[0].method is ResolutionMethod.COVERAGE_WEIGHTS

    weights = [o.coverage_weight for o in mfa.options]
    # Coverage is the best single mechanism, never the sum of the pieces: adding
    # 0.9 + 0.7 + 0.6 + ... would manufacture a coverage the catalog never claims.
    assert mfa.coverage == max(weights)
    assert mfa.coverage < sum(weights)


def test_residual_coverage_becomes_an_explicit_gap(resolution_a: ProfileResolution) -> None:
    malware = _capability(resolution_a, ZONE_OT, MALWARE)
    assert malware.gap is not None
    assert malware.gap.kind is GapKind.RESIDUAL_COVERAGE
    assert malware.gap.coverage == 0.9
    assert malware.gap.residual == 0.1


def test_contextual_overlays_do_not_count_as_coverage(resolution_a: ProfileResolution) -> None:
    report = _capability(resolution_a, ZONE_OT, REPORT)
    contextual = [o for o in report.options if o.mapping_type.value == "contextual"]
    assert {o.control_id for o in contextual} == {"CTL-NIS2-A23", "CTL-IMO-42898"}
    # They stay visible (they feed the regional delta) but are not a mechanism.
    assert all(o.status is CandidateStatus.ELIGIBLE for o in contextual)
    assert all(o.status_reason for o in contextual)
    assert report.coverage == 1.0  # from CSF RS.CO-02, not from the overlays


# --- Real contradiction ------------------------------------------------------


def test_contradiction_in_an_ot_zone_is_settled_by_ics_precedence(
    resolution_a: ProfileResolution,
) -> None:
    malware = _capability(resolution_a, ZONE_OT, MALWARE)
    contradiction = next(
        c for c in malware.conflicts if c.conflict_type is ConflictType.CONTRADICTION
    )
    assert contradiction.method is ResolutionMethod.FRAMEWORK_PRECEDENCE
    assert contradiction.prevailing_control_ids == [IEC_MALWARE]
    assert contradiction.superseded_control_ids == [CIS_MALWARE]
    assert contradiction.rule_id == "CONTRA-MALWARE-AGENT-OT"


def test_the_superseded_option_is_marked_not_removed(resolution_a: ProfileResolution) -> None:
    malware = _capability(resolution_a, ZONE_OT, MALWARE)
    superseded = next(o for o in malware.options if o.control_id == CIS_MALWARE)
    assert superseded.status is CandidateStatus.SUPERSEDED
    assert superseded.status_reason
    assert superseded.rule_id == "CONTRA-MALWARE-AGENT-OT"
    # Still on the table, still traceable — the human can see what was set aside.
    assert CIS_MALWARE in {o.control_id for o in malware.options}


def test_the_same_contradiction_resolves_the_other_way_in_a_hybrid_zone(
    resolution_b: ProfileResolution,
) -> None:
    malware = _capability(resolution_b, ZONE_ENG, MALWARE)
    contradiction = next(
        c for c in malware.conflicts if c.conflict_type is ConflictType.CONTRADICTION
    )
    # Same catalog, same rule, different zone: the context decides the mechanism.
    assert contradiction.prevailing_control_ids == [CIS_MALWARE]
    assert contradiction.superseded_control_ids == [IEC_MALWARE]


def test_the_most_restrictive_control_does_not_win_by_being_restrictive(
    resolution_a: ProfileResolution, resolution_b: ProfileResolution
) -> None:
    ot = _capability(resolution_a, ZONE_OT, MALWARE)
    hybrid = _capability(resolution_b, ZONE_ENG, MALWARE)
    strengths = {o.control_id: o.control.strength for o in ot.options}
    # IEC SR 3.2 is the more demanding of the two ("requerido a SL2-3" vs CIS "IG1")
    # and it still loses in the hybrid zone.
    assert strengths[IEC_MALWARE] != strengths[CIS_MALWARE]
    ot_winner = next(o for o in ot.options if o.status is not CandidateStatus.SUPERSEDED)
    hybrid_winner = next(o for o in hybrid.options if o.status is not CandidateStatus.SUPERSEDED)
    assert ot_winner.control_id == IEC_MALWARE
    assert hybrid_winner.control_id == CIS_MALWARE


# --- OT safety override ------------------------------------------------------


def test_safety_override_hands_the_decision_to_the_human(resolution_a: ProfileResolution) -> None:
    for zone_id in (ZONE_OT, ZONE_SIS):
        mfa = _capability(resolution_a, zone_id, MFA)
        override = next(
            c for c in mfa.conflicts if c.method is ResolutionMethod.SAFETY_OVERRIDE
        )
        assert override.requires_human_decision is True
        # The engine picks nothing and discards nothing.
        assert override.prevailing_control_ids == []
        assert override.superseded_control_ids == []
        contested = [o for o in mfa.options if o.status is CandidateStatus.CONTESTED]
        assert {o.control_id for o in contested} == {
            "CTL-CIS-0605",
            "CTL-IEC-SR17",
            "CTL-IEC-SR113",
        }


def test_the_capability_stays_required_under_the_safety_override(
    resolution_a: ProfileResolution,
) -> None:
    mfa = _capability(resolution_a, ZONE_OT, MFA)
    # Contested mechanisms still count as coverage: what is escalated is the
    # choice of mechanism, never the requirement itself.
    assert mfa.has_full_mechanism is True
    assert mfa.coverage == 0.9


def test_the_override_does_not_fire_where_it_does_not_apply(
    resolution_b: ProfileResolution,
) -> None:
    mfa = _capability(resolution_b, ZONE_ENG, MFA)
    assert [c for c in mfa.conflicts if c.method is ResolutionMethod.SAFETY_OVERRIDE] == []
    assert resolution_b.open_decisions == []
    assert all(o.status is not CandidateStatus.CONTESTED for o in mfa.options)


def test_open_decisions_are_surfaced_at_profile_level(resolution_a: ProfileResolution) -> None:
    open_ids = {c.rule_id for c in resolution_a.open_decisions}
    assert open_ids == {"CONTRA-AUTH-EMERGENCY-ACCESS"}
    assert len(resolution_a.open_decisions) == 2  # one per OT zone of the profile
