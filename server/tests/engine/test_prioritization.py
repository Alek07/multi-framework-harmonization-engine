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
from app.engine.prioritization_rules import CapabilityDependency, PrioritizationRules
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

ANOMALY = "CAP-DE-ANOMALY"
ASSET = "CAP-ID-ASSET"
CONTEXT = "CAP-GOV-CONTEXT"
DATACONF = "CAP-PR-DATACONF"
IDRISK = "CAP-ID-RISK"
IMPROVE = "CAP-ID-IMPROVE"
MEDIA = "CAP-PR-MEDIA"
MFA = "CAP-PR-MFA"
PAM = "CAP-PR-PAM"
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
    # The jurisdiction travels with the mandate — it is the matter of the regional
    # delta. This onshore pipeline is governed on both sides now (UCM-48): the
    # European obligation (NIS2) and the US one (CIRCIA transversal + TSA SD-01,
    # since the asset is 'transport'). The maritime obligation does not govern its
    # sector (UCM-47), so it creates no mandate.
    assert {m.jurisdiction for m in legal} == {Jurisdiction.EU, Jurisdiction.US}
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
    # Whatever tier it sits in, a capability answered off the asset is never an
    # open mandate of the asset: nothing on the zone can close it.
    assert all(not c.outstanding for c in organizational)
    # And the obligation did not evaporate with the deferral — most of these are
    # still Tier 0, they are just Tier 0 somewhere else.
    assert any(c.tier is PriorityTier.TIER_0 for c in organizational)


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
    # Cheap and high benefit: first.
    context = zone.capability(CONTEXT)
    assert (context.benefit, context.cost, context.priority) == (
        OrdinalLevel.HIGH,
        OrdinalLevel.LOW,
        OrdinalLevel.HIGH,
    )
    assert context.phase == 1
    # Same benefit reading, expensive: it is not dropped, it is scheduled later.
    anomaly = zone.capability(ANOMALY)
    assert (anomaly.benefit, anomaly.cost, anomaly.priority) == (
        OrdinalLevel.HIGH,
        OrdinalLevel.HIGH,
        OrdinalLevel.MEDIUM,
    )
    assert anomaly.phase == 2
    # Low benefit and not free: last, but still on the roadmap and still justified.
    improve = zone.capability(IMPROVE)
    assert (improve.benefit, improve.cost, improve.priority) == (
        OrdinalLevel.LOW,
        OrdinalLevel.MEDIUM,
        OrdinalLevel.LOW,
    )
    assert improve.phase == 3


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
    assert uplifted.gap is not None  # and it only applies where gating left something open

    moderate = profile_a.model_copy(deep=True)
    moderate.criticality.scale = ConsequenceScale.MODERATE
    other = _prioritize(moderate, catalog, rules, gating_rules, prioritization_rules)

    plain = other.zone(ZONE_SIS).capability(MEDIA)
    assert other.zone(ZONE_SIS).zone.safety_relevant is True
    assert plain.benefit is OrdinalLevel.LOW
    assert plain.coverage_level is uplifted.coverage_level


def test_the_cis_implementation_groups_order_it_zones_and_only_it_zones(
    priorities_a: ProfilePrioritization, priorities_b: ProfilePrioritization
) -> None:
    hybrid = [c for c in priorities_b.zone(ZONE_ENG).tier_1 if c.phase == 2]
    groups = [c.implementation_group for c in hybrid]
    # A ready-made IT prioritisation, reused: IG1 before IG2, and a capability
    # with no CIS mechanism left carries no group rather than a fabricated one.
    assert groups == ["IG1", "IG2", None]

    # The same phase in the OT zone holds the same two graded capabilities in the
    # opposite order: IG2 lands before IG1 because the IG does not order here at
    # all — it is an IT scale, recorded and declared informative. What orders in
    # the control zone is cost, and then the name.
    ot = [c.capability_id for c in priorities_a.zone(ZONE_OT).tier_1 if c.phase == 2]
    assert ot.index(ANOMALY) < ot.index(PAM)  # IG2 before IG1: the group did not decide
    hybrid_ids = [c.capability_id for c in hybrid]
    assert hybrid_ids.index(PAM) < hybrid_ids.index(ANOMALY)  # IG1 before IG2: here it did

    graded = [
        c
        for c in priorities_a.zone(ZONE_OT).tier_1
        if c.phase == 2 and c.implementation_group
    ]
    assert graded and all("informativo" in c.rationale for c in graded)


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
    """Cheap work that depends on expensive work does not jump the queue.

    The prerequisite is declared here rather than borrowed from the shipped rules
    on purpose: what is under test is the ordering mechanic, and pinning it to
    whichever pair of capabilities happens to share a tier would make the test
    fail every time the catalog grows.
    """
    tweaked = prioritization_rules.model_copy(deep=True)
    tweaked.dependencies.append(
        CapabilityDependency(
            capability_id=CONTEXT,
            requires=[ANOMALY],
            rationale="dependencia declarada por la prueba, no del catálogo",
        )
    )

    zone = _prioritize(profile_a, catalog, rules, gating_rules, tweaked).zone(ZONE_OT)
    context, anomaly = zone.capability(CONTEXT), zone.capability(ANOMALY)

    assert context.priority is OrdinalLevel.HIGH  # on its own it belongs in phase 1
    assert anomaly.phase == 2
    assert context.phase == 2  # but its prerequisite is not ready until phase 2
    assert "prerrequisito" in context.rationale


def test_a_mandate_is_never_deferred_by_a_discretionary_prerequisite(
    profile_a: AssetProfile,
    catalog: Catalog,
    rules: RuleSet,
    gating_rules: GatingRules,
    prioritization_rules: PrioritizationRules,
) -> None:
    """A Tier 0 mandate lands in phase 0 even when a Tier 1 prerequisite is not ready.

    The prerequisite is declared by the test rather than borrowed from the shipped
    rules on purpose: once the US legal corpus (UCM-48) made the TSA gap assessment
    (CAP-ID-RISK) a legal mandate for this pipeline, both ends of the catalog's
    PATCH←ID-RISK edge are Tier 0, so the ordering mechanic needs a pair that is
    still one mandate and one discretionary capability. Patch management is Tier 0
    (NIS2 obliges it); organizational context is discretionary here.
    """
    # CAP-ID-ASSET is Tier 0 here (NIS2 obliges asset management) and carries no
    # shipped prerequisite, so the test-declared edge is the only one it has.
    tweaked = prioritization_rules.model_copy(deep=True)
    tweaked.dependencies.append(
        CapabilityDependency(
            capability_id=ASSET,
            requires=[CONTEXT],
            rationale="dependencia declarada por la prueba, no del catálogo",
        )
    )

    zone = _prioritize(profile_a, catalog, rules, gating_rules, tweaked).zone(ZONE_OT)
    context, asset = zone.capability(CONTEXT), zone.capability(ASSET)

    assert context.tier is PriorityTier.TIER_1
    assert asset.tier is PriorityTier.TIER_0
    assert asset.phase == MANDATORY_PHASE
    assert context.phase > MANDATORY_PHASE
    # The engine does not hide the sequencing it refused to impose.
    assert CONTEXT in asset.depends_on
    assert ASSET in context.unlocks


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
    sis = priorities_a.zone(ZONE_SIS).capability(MEDIA)
    hybrid = priorities_b.zone(ZONE_ENG).capability(MEDIA)
    # The crown jewel accepts no portable media at all, so it is left with the
    # compensatory mapping alone; the workstation keeps the OS mechanism. Same
    # catalog, same capability, two readings.
    assert sis.coverage < hybrid.coverage
    assert sis.implementation_group is None
    assert hybrid.implementation_group == "IG1"

    ot_order = [c.capability_id for c in priorities_a.zone(ZONE_OT).tier_1]
    hybrid_order = [c.capability_id for c in priorities_b.zone(ZONE_ENG).tier_1]
    assert ot_order != hybrid_order


def test_prioritization_reports_the_versions_it_ran_with(
    priorities_a: ProfilePrioritization,
) -> None:
    assert priorities_a.catalog_version == "0.6.0"
    assert priorities_a.rules_version == "0.2.0"
    assert priorities_a.gating_version == "0.3.0"
    assert priorities_a.prioritization_version == "0.2.0"


def test_an_unknown_zone_is_an_error_not_an_empty_roadmap(
    priorities_a: ProfilePrioritization,
) -> None:
    with pytest.raises(KeyError, match="zone not prioritised"):
        priorities_a.zone("Z-DOES-NOT-EXIST")
