"""UCM-11 - What the log says about a core run, before it touches the database.

The derivation is pure, so the promise of the research question can be measured
directly on it: every decision has an author and a written reason, nothing the
engine found is left out, and the same run always produces the same trail.
"""

import pytest
from pydantic import ValidationError

from app.assets.schemas import AssetProfile
from app.audit.schemas import (
    AuditActor,
    AuditEventCreate,
    AuditEventType,
    AuditStage,
)
from app.audit.trail import trail_for_core_run
from app.catalog.schemas import Catalog
from app.engine.schemas import (
    CapabilityStatus,
    ProfileGating,
    ProfilePrioritization,
    ProfileResolution,
)
from tests.audit.conftest import RUN_A


def test_every_entry_says_who_what_and_why(
    trail_a: list[AuditEventCreate], trail_b: list[AuditEventCreate]
) -> None:
    """The central promise: no anonymous decision, no unjustified decision."""
    for trail in (trail_a, trail_b):
        for entry in trail:
            assert entry.actor is AuditActor.ENGINE
            assert entry.actor_ref, entry.event_type
            assert entry.decision.strip()
            assert entry.rationale.strip()
            assert entry.profile_id
            # Reproducibility travels with the decision, not just with the run.
            assert entry.versions == {
                "catalog": "0.5.0",
                "rules": "0.1.0",
                "gating": "0.2.0",
                "prioritization": "0.2.0",
            }


def test_the_trail_follows_the_pipeline(trail_a: list[AuditEventCreate]) -> None:
    """run -> mapping -> conflict resolution -> gating -> prioritisation -> run."""
    assert trail_a[0].event_type is AuditEventType.RUN_STARTED
    assert trail_a[-1].event_type is AuditEventType.RUN_COMPLETED

    order = [
        AuditStage.RUN,
        AuditStage.MAPPING,
        AuditStage.CONFLICT_RESOLUTION,
        AuditStage.GATING,
        AuditStage.PRIORITIZATION,
        AuditStage.RUN,
    ]
    stages = [entry.stage for entry in trail_a]
    collapsed = [stage for i, stage in enumerate(stages) if i == 0 or stage is not stages[i - 1]]
    assert collapsed == order


def test_every_capability_of_every_zone_leaves_a_mark(
    trail_a: list[AuditEventCreate],
    trail_b: list[AuditEventCreate],
    resolution_a: ProfileResolution,
    resolution_b: ProfileResolution,
    catalog: Catalog,
) -> None:
    """0 silent omissions, measured on the log itself and not on the return value."""
    for trail, resolution in ((trail_a, resolution_a), (trail_b, resolution_b)):
        mapped = {
            (entry.zone_id, entry.capability_id)
            for entry in trail
            if entry.event_type is AuditEventType.CAPABILITY_MAPPED
        }
        expected = {
            (zone.zone.zone_id, capability.capability.id)
            for zone in resolution.zones
            for capability in zone.capabilities
        }
        assert mapped == expected
        assert len(mapped) == len(catalog.capabilities) * len(resolution.zones)

        # And each stage closes by naming what it accounted for.
        for stage in (AuditStage.MAPPING, AuditStage.GATING):
            closings = [
                entry
                for entry in trail
                if entry.stage is stage and entry.event_type is AuditEventType.STAGE_COMPLETED
            ]
            assert len(closings) == len(resolution.zones)
            for closing in closings:
                assert len(closing.payload["capability_ids"]) == len(catalog.capabilities)


def test_no_gap_and_no_open_decision_goes_unrecorded(
    trail_a: list[AuditEventCreate],
    resolution_a: ProfileResolution,
    gating_a: ProfileGating,
) -> None:
    """What the engine could not cover is on the record — that is what a gap is for."""
    declared = {
        (entry.zone_id, entry.capability_id)
        for entry in trail_a
        if entry.event_type is AuditEventType.GAP_DECLARED
    }
    carried_over = {
        (entry.zone_id, capability_id)
        for entry in trail_a
        if entry.event_type is AuditEventType.STAGE_COMPLETED
        for capability_id in entry.payload.get("gaps_carried_over", [])
    }
    for gap in list(resolution_a.gaps) + list(gating_a.gaps):
        assert (gap.zone_id, gap.capability_id) in declared | carried_over

    escalated = {
        entry.payload["id"]
        for entry in trail_a
        if entry.event_type is AuditEventType.CONFLICT_ESCALATED
    }
    assert escalated == {conflict.id for conflict in resolution_a.open_decisions}
    assert escalated, "profile A has real contradictions and they must reach the human"


def test_every_engine_decision_is_recorded_once(
    trail_a: list[AuditEventCreate],
    resolution_a: ProfileResolution,
    gating_a: ProfileGating,
    priorities_a: ProfilePrioritization,
) -> None:
    counts: dict[AuditEventType, int] = {}
    for entry in trail_a:
        counts[entry.event_type] = counts.get(entry.event_type, 0) + 1

    resolved = len(resolution_a.conflicts) - len(resolution_a.open_decisions)
    assert counts.get(AuditEventType.CONFLICT_RESOLVED, 0) == resolved
    assert counts[AuditEventType.CONFLICT_ESCALATED] == len(resolution_a.open_decisions)
    assert counts[AuditEventType.MECHANISM_EXCLUDED] == len(gating_a.decisions)
    assert counts[AuditEventType.CAPABILITY_STATUS_SET] == len(
        [
            capability
            for zone in gating_a.zones
            for capability in zone.capabilities
            if capability.status is not CapabilityStatus.COVERED_BY_MECHANISM
        ]
    )

    tier_0 = [c for zone in priorities_a.zones for c in zone.tier_0]
    tier_1 = [c for zone in priorities_a.zones for c in zone.tier_1]
    assert counts[AuditEventType.MANDATE_RECORDED] == len(tier_0)
    assert counts[AuditEventType.PRIORITY_ASSIGNED] == len(tier_1)
    assert counts.get(AuditEventType.MANDATE_OUTSTANDING, 0) == len(
        priorities_a.outstanding_mandates
    )
    assert counts[AuditEventType.ROADMAP_PHASED] == len(priorities_a.zones)


def test_the_rule_that_fired_is_named(
    trail_a: list[AuditEventCreate], gating_a: ProfileGating
) -> None:
    """A decision "por regla" that does not name the rule is not traceable."""
    excluded = [
        entry for entry in trail_a if entry.event_type is AuditEventType.MECHANISM_EXCLUDED
    ]
    assert len(excluded) == len(gating_a.decisions)
    for entry in excluded:
        assert entry.rule_id
        assert entry.control_id
        # The premises read from the profile that made the rule fire.
        assert entry.payload["evidence"]


def test_the_trail_is_reproducible(
    profile_a: AssetProfile,
    resolution_a: ProfileResolution,
    gating_a: ProfileGating,
    priorities_a: ProfilePrioritization,
    trail_a: list[AuditEventCreate],
) -> None:
    """Same run in, same trail out: only time and position come from the ledger."""
    again = trail_for_core_run(profile_a, resolution_a, gating_a, priorities_a, RUN_A)
    assert again == trail_a


def test_the_two_profiles_produce_different_trails(
    trail_a: list[AuditEventCreate], trail_b: list[AuditEventCreate]
) -> None:
    """Same catalog, different asset: the log has to show the difference."""
    excluded_a = {
        entry.control_id
        for entry in trail_a
        if entry.event_type is AuditEventType.MECHANISM_EXCLUDED
    }
    excluded_b = {
        entry.control_id
        for entry in trail_b
        if entry.event_type is AuditEventType.MECHANISM_EXCLUDED
    }
    assert excluded_a and excluded_b
    assert excluded_a != excluded_b


def test_a_trail_stitched_from_two_runs_is_refused(
    profile_a: AssetProfile,
    resolution_a: ProfileResolution,
    gating_b: ProfileGating,
    priorities_a: ProfilePrioritization,
) -> None:
    """A plausible-looking lie is worse than no log at all."""
    with pytest.raises(ValueError, match="mixes asset profiles"):
        trail_for_core_run(profile_a, resolution_a, gating_b, priorities_a, RUN_A)


def test_an_engine_decision_cannot_be_filed_as_a_human_one() -> None:
    with pytest.raises(ValidationError, match="authored by 'engine'"):
        AuditEventCreate(
            actor=AuditActor.HUMAN,
            stage=AuditStage.GATING,
            event_type=AuditEventType.MECHANISM_EXCLUDED,
            run_id=RUN_A,
            profile_id="PROFILE-A",
            decision="…",
            rationale="…",
        )


def test_a_human_choice_cannot_be_filed_as_an_engine_one() -> None:
    with pytest.raises(ValidationError, match="authored by 'human'"):
        AuditEventCreate(
            actor=AuditActor.ENGINE,
            stage=AuditStage.SIGNATURE,
            event_type=AuditEventType.BASELINE_SIGNED,
            run_id=RUN_A,
            profile_id="PROFILE-A",
            decision="…",
            rationale="…",
        )


@pytest.mark.parametrize("blank", ["", "   ", "\n"])
def test_a_decision_without_a_written_reason_is_not_recordable(blank: str) -> None:
    with pytest.raises(ValidationError):
        AuditEventCreate(
            actor=AuditActor.HUMAN,
            stage=AuditStage.COMPOSITION,
            event_type=AuditEventType.OPTION_SELECTED,
            run_id=RUN_A,
            profile_id="PROFILE-A",
            decision="Se elige IEC62443 SR 1.1 para la zona Z-OT-CORRIDOR",
            rationale=blank,
        )
