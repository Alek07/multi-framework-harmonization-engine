"""UCM-10 - Step 4: two tiers that are never ranked against each other.

Tier 0 is what the zone's SL-target (or the law) makes obligatory: it is not
prioritised, it is completed. Tier 1 is the only thing the engine orders, and it
orders it with ordinal scales and a declared table — no invented numbers. The
dependencies are a partial order, the CIS Implementation Groups are reused where
they belong, and every capability of the catalog ends up in exactly one phase.
"""

import pytest

from app.assets.schemas import AssetProfile, ConsequenceScale
from app.catalog.schemas import Catalog, Jurisdiction
from app.engine.gating_rules import GatingRules
from app.engine.prioritization_rules import PrioritizationRules
from app.engine.rules import RuleSet
from app.engine.schemas import (
    ImplementationLayer,
    MandateSource,
    OrdinalLevel,
    PriorityTier,
    ProfilePrioritization,
)
from app.engine.service import gate_profile, prioritize_profile, resolve_profile
from tests.engine.conftest import ZONE_ENG, ZONE_OT, ZONE_SIS

ASSET = "CAP-ID-ASSET"
DATACONF = "CAP-PR-DATACONF"
IDRISK = "CAP-ID-RISK"
MEDIA = "CAP-PR-MEDIA"
MFA = "CAP-PR-MFA"
PATCH = "CAP-PR-PATCH"
REPORT = "CAP-RS-REPORT"
SEGMENT = "CAP-PR-SEGMENT"

MANDATORY_PHASE = 0


def _prioritize(
    profile: AssetProfile,
    catalog: Catalog,
    rules: RuleSet,
    gating_rules: GatingRules,
    prioritization_rules: PrioritizationRules,
) -> ProfilePrioritization:
    """The whole core, steps 1-4, for a profile the fixtures do not freeze."""
    resolution = resolve_profile(profile, catalog, rules)
    gating = gate_profile(profile, resolution, gating_rules, catalog)
    return prioritize_profile(profile, gating, prioritization_rules, catalog)


# --- Tier 0: obligatory, and therefore not ranked -----------------------------


def test_tier_0_is_not_prioritized_it_is_completed(priorities_a: ProfilePrioritization) -> None:
    for zone in priorities_a.zones:
        assert zone.tier_0
        for capability in zone.tier_0:
            # Null by contract, not a missing value: what is mandatory is not ranked.
            assert capability.priority is None
            assert capability.phase == MANDATORY_PHASE
            assert capability.mandates


def test_the_mandatory_phase_is_listed_alphabetically_not_ranked(
    priorities_a: ProfilePrioritization,
) -> None:
    phase = priorities_a.zone(ZONE_OT).phase(MANDATORY_PHASE)
    assert phase.tier is PriorityTier.TIER_0
    assert phase.capability_ids == sorted(phase.capability_ids)


def test_tier_0_is_read_from_the_zones_sl_target_per_foundational_requirement(
    profile_a: AssetProfile,
    catalog: Catalog,
    rules: RuleSet,
    gating_rules: GatingRules,
    prioritization_rules: PrioritizationRules,
) -> None:
    """Same catalog, a lower SL-target on one FR, a different mandatory block."""
    baseline = _prioritize(profile_a, catalog, rules, gating_rules, prioritization_rules)
    assert baseline.zone(ZONE_OT).capability(DATACONF).tier is PriorityTier.TIER_0

    lowered = profile_a.model_copy(deep=True)
    assert lowered.zones[0].sl_vector is not None
    lowered.zones[0].sl_vector.FR4 = 1  # confidentiality below the SL that mandates SR 4.1

    other = _prioritize(lowered, catalog, rules, gating_rules, prioritization_rules)
    dataconf = other.zone(ZONE_OT).capability(DATACONF)
    assert dataconf.tier is PriorityTier.TIER_1
    assert dataconf.mandates == []
    # The zone next door keeps its own reading: tiering is per zone, not per catalog.
    assert other.zone(ZONE_SIS).capability(DATACONF).tier is PriorityTier.TIER_0


def test_an_sl_mandate_carries_the_evidence_that_supports_it(
    priorities_a: ProfilePrioritization,
) -> None:
    mandate = next(
        m
        for m in priorities_a.zone(ZONE_OT).capability(SEGMENT).mandates
        if m.source is MandateSource.SL_TARGET
    )
    assert mandate.official_id == "SR 5.1"
    assert mandate.foundational_requirement is not None
    assert mandate.required_at_sl == 1
    assert mandate.zone_sl_target == 3
    assert mandate.rationale.strip()


def test_a_legal_obligation_is_mandatory_whatever_the_sl_target_says(
    priorities_a: ProfilePrioritization,
) -> None:
    report = priorities_a.zone(ZONE_OT).capability(REPORT)
    assert report.tier is PriorityTier.TIER_0
    legal = [m for m in report.mandates if m.source is MandateSource.LEGAL_OBLIGATION]
    # The jurisdiction travels with the mandate — it is the matter of the regional delta.
    assert {m.jurisdiction for m in legal} == {Jurisdiction.EU, Jurisdiction.INTL_MARITIME}
    # Gating deferred it to the organizational layer; the obligation did not disappear.
    assert report.layer is ImplementationLayer.ORGANIZATIONAL


def test_a_mandate_survives_the_gating_that_could_not_meet_it(
    priorities_a: ProfilePrioritization,
) -> None:
    """The asset cannot host the mechanism; that does not repeal the requirement."""
    mfa = priorities_a.zone(ZONE_OT).capability(MFA)
    assert mfa.tier is PriorityTier.TIER_0
    assert mfa.outstanding is True
    assert mfa.gap is not None
    assert mfa.rationale.strip()


def test_the_outstanding_list_is_the_pre_signature_checklist(
    priorities_a: ProfilePrioritization, priorities_b: ProfilePrioritization
) -> None:
    for priorities in (priorities_a, priorities_b):
        outstanding = priorities.outstanding_mandates
        assert outstanding
        assert priorities.tier_0_complete is False
        for capability in outstanding:
            assert capability.tier is PriorityTier.TIER_0
            # Never a bare flag: what is missing is always said.
            assert capability.gap is not None or capability.status.value == "compensatory_required"
            assert capability.rationale.strip()


def test_a_capability_answered_off_the_asset_is_not_an_open_asset_gap(
    priorities_a: ProfilePrioritization,
) -> None:
    organizational = [
        c
        for c in priorities_a.zone(ZONE_OT).capabilities
        if c.layer is ImplementationLayer.ORGANIZATIONAL
    ]
    assert organizational
    assert all(not c.outstanding for c in organizational)
    assert all(c.tier is PriorityTier.TIER_0 for c in organizational)


# --- Tier 1: the only thing the engine orders, and only ordinally -------------


def test_tier_1_is_ordered_with_ordinal_scales_and_nothing_else(
    priorities_a: ProfilePrioritization, priorities_b: ProfilePrioritization
) -> None:
    for priorities in (priorities_a, priorities_b):
        for zone in priorities.zones:
            assert zone.tier_1
            for capability in zone.tier_1:
                assert isinstance(capability.priority, OrdinalLevel)
                assert isinstance(capability.benefit, OrdinalLevel)
                assert isinstance(capability.cost, OrdinalLevel)
                assert capability.mandates == []
                assert capability.phase >= 1


def test_the_declared_table_turns_benefit_and_cost_into_a_phase(
    priorities_a: ProfilePrioritization,
) -> None:
    zone = priorities_a.zone(ZONE_OT)
    # Cheap and with something open in a catastrophic-consequence zone: first.
    media = zone.capability(MEDIA)
    assert (media.benefit, media.cost, media.priority) == (
        OrdinalLevel.MEDIUM,
        OrdinalLevel.LOW,
        OrdinalLevel.HIGH,
    )
    assert media.phase == 1
    # Same benefit reading, expensive: it is not dropped, it is scheduled later.
    patch = zone.capability(PATCH)
    assert (patch.benefit, patch.cost, patch.priority) == (
        OrdinalLevel.HIGH,
        OrdinalLevel.HIGH,
        OrdinalLevel.MEDIUM,
    )
    assert patch.phase == 2


def test_the_physical_consequence_raises_the_benefit_instead_of_inventing_a_number(
    profile_a: AssetProfile,
    catalog: Catalog,
    rules: RuleSet,
    gating_rules: GatingRules,
    prioritization_rules: PrioritizationRules,
) -> None:
    """Z-SIS stays safety-relevant on its own; only the consequence changes."""
    baseline = _prioritize(profile_a, catalog, rules, gating_rules, prioritization_rules)
    uplifted = baseline.zone(ZONE_SIS).capability(MEDIA)
    assert uplifted.benefit is OrdinalLevel.MEDIUM
    assert uplifted.coverage_level is OrdinalLevel.LOW  # the uplift is the whole difference
    assert "escalón" in uplifted.rationale

    moderate = profile_a.model_copy(deep=True)
    moderate.criticality.scale = ConsequenceScale.MODERATE
    other = _prioritize(moderate, catalog, rules, gating_rules, prioritization_rules)

    plain = other.zone(ZONE_SIS).capability(MEDIA)
    assert other.zone(ZONE_SIS).zone.safety_relevant is True
    assert plain.benefit is OrdinalLevel.LOW
    assert plain.priority is OrdinalLevel.MEDIUM
    assert plain.phase > uplifted.phase


def test_the_cis_implementation_groups_order_it_zones_and_only_it_zones(
    priorities_a: ProfilePrioritization, priorities_b: ProfilePrioritization
) -> None:
    hybrid = [c for c in priorities_b.zone(ZONE_ENG).tier_1 if c.phase == 2]
    groups = [c.implementation_group for c in hybrid]
    assert groups == ["IG1", "IG1", "IG2"]  # a ready-made IT prioritisation, reused

    # In the OT zone the same three sit in alphabetical order: the IG is recorded
    # but it does not order — it is an IT scale.
    ot = [c for c in priorities_a.zone(ZONE_OT).tier_1 if c.phase == 2]
    assert [c.capability_id for c in ot] == sorted(c.capability_id for c in ot)
    assert any(c.implementation_group for c in ot)
    assert all("informativo" in c.rationale for c in ot if c.implementation_group)


# --- Dependencies: a partial order, never a ranking ---------------------------


def test_nothing_is_scheduled_before_what_enables_it(
    priorities_a: ProfilePrioritization,
    priorities_b: ProfilePrioritization,
    prioritization_rules: PrioritizationRules,
) -> None:
    for priorities in (priorities_a, priorities_b):
        for zone in priorities.zones:
            for capability in zone.tier_1:
                for prerequisite in prioritization_rules.requires(capability.capability_id):
                    assert zone.capability(prerequisite).phase <= capability.phase


def test_a_late_prerequisite_pushes_its_dependant_back(
    profile_a: AssetProfile,
    catalog: Catalog,
    rules: RuleSet,
    gating_rules: GatingRules,
    prioritization_rules: PrioritizationRules,
) -> None:
    """Cheap work that depends on expensive work does not jump the queue."""
    tweaked = prioritization_rules.model_copy(deep=True)
    for cost in tweaked.costs:
        if cost.capability_id == PATCH:
            cost.cost = OrdinalLevel.LOW
        if cost.capability_id == IDRISK:
            cost.cost = OrdinalLevel.HIGH

    zone = _prioritize(profile_a, catalog, rules, gating_rules, tweaked).zone(ZONE_OT)
    patch, risk = zone.capability(PATCH), zone.capability(IDRISK)

    assert patch.priority is OrdinalLevel.HIGH  # on its own it belongs in phase 1
    assert risk.phase == 2
    assert patch.phase == 2  # but its prerequisite is not ready until phase 2
    assert "prerrequisito" in patch.rationale


def test_a_mandate_is_never_deferred_by_a_discretionary_prerequisite(
    profile_a: AssetProfile,
    catalog: Catalog,
    rules: RuleSet,
    gating_rules: GatingRules,
    prioritization_rules: PrioritizationRules,
) -> None:
    """Lower FR7 and the asset inventory stops being mandatory — segmentation does not."""
    lowered = profile_a.model_copy(deep=True)
    assert lowered.zones[0].sl_vector is not None
    lowered.zones[0].sl_vector.FR7 = 1  # below the SL that mandates SR 7.8 (inventory)

    zone = _prioritize(lowered, catalog, rules, gating_rules, prioritization_rules).zone(ZONE_OT)
    inventory, segmentation = zone.capability(ASSET), zone.capability(SEGMENT)

    assert inventory.tier is PriorityTier.TIER_1
    assert segmentation.tier is PriorityTier.TIER_0
    assert segmentation.phase == MANDATORY_PHASE
    assert inventory.phase > MANDATORY_PHASE
    # The engine does not hide the sequencing it refused to impose.
    assert ASSET in segmentation.depends_on
    assert SEGMENT in inventory.unlocks


# --- The roadmap leaves nothing out ------------------------------------------


def test_every_capability_of_the_catalog_lands_in_exactly_one_phase(
    priorities_a: ProfilePrioritization, priorities_b: ProfilePrioritization, catalog: Catalog
) -> None:
    for priorities in (priorities_a, priorities_b):
        for zone in priorities.zones:
            assert {c.capability_id for c in zone.capabilities} == catalog.capability_ids
            scheduled = [cid for phase in zone.phases for cid in phase.capability_ids]
            assert sorted(scheduled) == sorted(catalog.capability_ids)


def test_the_roadmap_declares_its_empty_phases_instead_of_hiding_them(
    priorities_a: ProfilePrioritization,
) -> None:
    zone = priorities_a.zone(ZONE_OT)
    assert [p.index for p in zone.phases] == [0, 1, 2, 3]
    assert all(p.name.strip() and p.rationale.strip() for p in zone.phases)


def test_prioritization_never_acts_in_silence(
    priorities_a: ProfilePrioritization, priorities_b: ProfilePrioritization
) -> None:
    for priorities in (priorities_a, priorities_b):
        for zone in priorities.zones:
            for capability in zone.capabilities:
                assert capability.rationale.strip(), capability.capability_id
                assert all(m.rationale.strip() for m in capability.mandates)


def test_the_same_catalog_produces_a_different_roadmap_per_zone(
    priorities_a: ProfilePrioritization, priorities_b: ProfilePrioritization
) -> None:
    ot = priorities_a.zone(ZONE_OT).capability(MEDIA)
    hybrid = priorities_b.zone(ZONE_ENG).capability(MEDIA)
    # Gating left the controller without the OS mechanism; the workstation kept it.
    assert ot.coverage < hybrid.coverage
    assert ot.implementation_group is None
    assert hybrid.implementation_group == "IG1"

    ot_order = [c.capability_id for c in priorities_a.zone(ZONE_OT).tier_1]
    hybrid_order = [c.capability_id for c in priorities_b.zone(ZONE_ENG).tier_1]
    assert ot_order != hybrid_order


def test_prioritization_reports_the_versions_it_ran_with(
    priorities_a: ProfilePrioritization,
) -> None:
    assert priorities_a.catalog_version == "0.1.0"
    assert priorities_a.rules_version == "0.1.0"
    assert priorities_a.gating_version == "0.1.0"
    assert priorities_a.prioritization_version == "0.1.0"


def test_an_unknown_zone_is_an_error_not_an_empty_roadmap(
    priorities_a: ProfilePrioritization,
) -> None:
    with pytest.raises(KeyError, match="zone not prioritised"):
        priorities_a.zone("Z-DOES-NOT-EXIST")
