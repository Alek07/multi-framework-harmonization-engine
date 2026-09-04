"""Step 1 of the core: map framework controls to neutral capabilities.

Collects every control mapped to each capability, in a deterministic order
independent of catalog ingestion. Selects and discards nothing.
"""

from __future__ import annotations

from app.catalog.schemas import Capability, Catalog, MappingType
from app.engine.rules import RuleSet
from app.engine.schemas import CandidateOption, ZoneContext

# Order in which options are shown side by side: broadest coverage first.
MAPPING_TYPE_RANK: dict[MappingType, int] = {
    MappingType.TOTAL: 0,
    MappingType.PARTIAL: 1,
    MappingType.COMPENSATORY: 2,
    MappingType.CONTEXTUAL: 3,
}


def build_options(
    catalog: Catalog, capability_id: str, rules: RuleSet, zone: ZoneContext
) -> list[CandidateOption]:
    """Every control mapped to the capability, in deterministic presentation order.

    Order is a reading convenience, not a decision: mapping breadth, coverage,
    zone precedence, then control ID as a stable tie-breaker.
    """
    controls = {c.id: c for c in catalog.controls}
    options = [
        CandidateOption(control=controls[m.control_id], mapping=m)
        for m in catalog.mappings_for(capability_id)
    ]
    options.sort(
        key=lambda o: (
            MAPPING_TYPE_RANK[o.mapping_type],
            -o.coverage_weight,
            rules.precedence_index(zone.domain, o.framework),
            o.control_id,
        )
    )
    return options


def map_zone(
    catalog: Catalog, rules: RuleSet, zone: ZoneContext
) -> list[tuple[Capability, list[CandidateOption]]]:
    """Candidates for every catalog capability in a zone; none is dropped.

    A capability with no candidate is carried as an empty list — an explicit
    gap downstream, never a silent omission.
    """
    return [
        (capability, build_options(catalog, capability.id, rules, zone))
        for capability in sorted(catalog.capabilities, key=lambda c: c.id)
    ]
