"""UCM-13 - The payload lens: what it asks Qdrant, and what it can never do."""

from __future__ import annotations

import pytest
from qdrant_client import models as qdrant

from app.assets.schemas import AssetProfile
from app.catalog.schemas import Framework, Jurisdiction, MappingType, Sector
from app.engine.rules import RuleSet
from app.engine.schemas import ZoneDomain
from app.engine.zones import zone_context
from app.retrieval.filters import excluded_axes, to_qdrant, zone_lens
from app.retrieval.index import ControlPayload
from app.retrieval.schemas import FilterAxis, PayloadFilter


def payload(**overrides: object) -> ControlPayload:
    base = {
        "control_id": "CTL-CIS-0501",
        "framework": "CIS",
        "official_id": "5.1",
        "title": "Establish and maintain an inventory of accounts",
        "jurisdiction": "US",
        "control_type": "technical",
        "strength": "IG1",
        "capability_ids": ["CAP-PR-IDENTITY"],
        "mapping_types": ["partial"],
        "provenance_sources": ["author_judgment"],
        "catalog_version": "0.1.0",
        "text": "…",
    }
    return ControlPayload.model_validate(base | overrides)


def test_no_lens_means_no_filter_on_the_wire() -> None:
    """An inactive lens is `None`, not an empty filter that happens to match all."""
    assert to_qdrant(None) is None
    assert to_qdrant(PayloadFilter()) is None
    assert PayloadFilter().is_active is False


def test_the_lens_declares_the_three_axes_of_the_ticket() -> None:
    lens = PayloadFilter(
        jurisdictions=[Jurisdiction.EU],
        frameworks=[Framework.IEC62443],
        mapping_types=[MappingType.TOTAL],
    )
    query_filter = to_qdrant(lens)

    assert lens.axes == [FilterAxis.JURISDICTION, FilterAxis.ZONE, FilterAxis.MAPPING_TYPE]
    assert query_filter is not None
    assert {condition.key for condition in query_filter.must} == {
        "jurisdiction",
        "framework",
        "mapping_types",
    }


def test_the_lens_says_in_writing_what_it_is_doing() -> None:
    """The operator and the log both read this string; it may not be empty."""
    assert "sin filtro" in PayloadFilter().describe()

    described = PayloadFilter(jurisdictions=[Jurisdiction.EU]).describe()
    assert "EU" in described and "jurisdicción" in described


def test_every_excluded_candidate_knows_which_axis_excluded_it() -> None:
    lens = PayloadFilter(jurisdictions=[Jurisdiction.EU], mapping_types=[MappingType.TOTAL])

    assert excluded_axes(lens, payload(jurisdiction="EU", mapping_types=["total"])) == []
    assert excluded_axes(lens, payload(jurisdiction="US", mapping_types=["total"])) == [
        FilterAxis.JURISDICTION
    ]
    assert excluded_axes(lens, payload(jurisdiction="US", mapping_types=["partial"])) == [
        FilterAxis.JURISDICTION,
        FilterAxis.MAPPING_TYPE,
    ]


def test_a_control_matches_a_mapping_type_it_serves_anywhere() -> None:
    """The unit indexed is the mechanism: "is it total *somewhere*" is the question."""
    lens = PayloadFilter(mapping_types=[MappingType.TOTAL])

    assert excluded_axes(lens, payload(mapping_types=["partial", "total"])) == []
    assert excluded_axes(lens, payload(mapping_types=["partial"])) == [FilterAxis.MAPPING_TYPE]


def test_the_sector_lens_never_excludes_a_transversal_control() -> None:
    """UCM-52: empty scope is transversal (UCM-47); only an enumerated, disjoint scope excludes."""
    lens = PayloadFilter(sectors=[Sector.ENERGY])

    assert excluded_axes(lens, payload(applies_to_sectors=[])) == []  # transversal
    assert excluded_axes(lens, payload(applies_to_sectors=["energy"])) == []
    assert excluded_axes(lens, payload(applies_to_sectors=["maritime", "energy"])) == []
    assert excluded_axes(lens, payload(applies_to_sectors=["maritime"])) == [FilterAxis.SECTOR]


def test_the_sector_lens_is_a_nested_or_on_the_wire() -> None:
    """Transversal *or* in scope must both survive, so the sector condition is a `should`."""
    query_filter = to_qdrant(PayloadFilter(sectors=[Sector.ENERGY]))

    assert query_filter is not None
    subfilters = [c for c in query_filter.must if isinstance(c, qdrant.Filter)]
    assert len(subfilters) == 1, "the sector axis is one nested sub-filter"
    branches = {type(branch).__name__ for branch in subfilters[0].should or []}
    assert branches == {"IsEmptyCondition", "FieldCondition"}


def test_the_zone_lens_reads_the_declared_precedence_and_invents_nothing(
    profile_a: AssetProfile, rules: RuleSet
) -> None:
    zone = zone_context(profile_a.zones[0], profile_a)
    lens = zone_lens(zone, rules, frameworks=2)

    assert zone.domain is ZoneDomain.OT
    assert lens.frameworks == rules.framework_precedence[ZoneDomain.OT][:2]
    assert lens.frameworks == [Framework.IEC62443, Framework.CSF]
    assert lens.zone_domain is ZoneDomain.OT
    # The rationale of the declared rule travels with the lens, so an operator can
    # see *why* this is the OT reading and not somebody's preference.
    assert rules.framework_precedence_rationale[ZoneDomain.OT] in lens.rationale


def test_an_it_zone_reads_a_different_lens_from_the_same_rules(
    profile_b: AssetProfile, rules: RuleSet
) -> None:
    zone = next(
        zone_context(z, profile_b)
        for z in profile_b.zones
        if zone_context(z, profile_b).domain is not ZoneDomain.OT
    )
    lens = zone_lens(zone, rules, frameworks=2)

    assert lens.frameworks == [Framework.CSF, Framework.CIS]


def test_a_zone_lens_cannot_keep_nothing(profile_a: AssetProfile, rules: RuleSet) -> None:
    zone = zone_context(profile_a.zones[0], profile_a)

    with pytest.raises(ValueError, match="at least one framework"):
        zone_lens(zone, rules, frameworks=0)
