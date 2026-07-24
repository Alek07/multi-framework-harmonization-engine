"""UCM-8 - Step 1 of the core: map framework controls to neutral capabilities.

The neutral capability is what dissolves the origin: CSF, IEC 62443, CIS, NIS2
and IMO stop being rival lists and become *options for the same outcome*. This
step collects, for every capability of the catalog, all the controls mapped to
it, in a deterministic order that does not depend on how the catalog was
ingested. It selects nothing and discards nothing — that is the human's job
(sovereign composition) and, for mechanisms, gating's (UCM-9).
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

    The order is a reading convenience, not a decision: it sorts by breadth of
    the mapping, then coverage weight, then the zone's framework precedence, and
    finally the control ID as tie-breaker so the result is stable.
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
    """Candidates for every capability of the catalog in a zone.

    Every capability is carried through, including those with no candidate:
    an empty list is an explicit gap downstream, never a silent omission.
    """
    return [
        (capability, build_options(catalog, capability.id, rules, zone))
        for capability in sorted(catalog.capabilities, key=lambda c: c.id)
    ]
