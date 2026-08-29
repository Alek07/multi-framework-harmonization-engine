"""UCM-13 - Payload filtering: a declared lens, never a silent narrowing.

The ticket asks for retrieval filtered by payload on three axes — jurisdiction,
zone and mapping type — and the project's second invariant says nothing may be
restricted in silence. Both hold at once because of how the filter is used, and
that is worth stating plainly:

* **Most axes are a human's question, not a policy.** "Show me the EU reading of
  this zone" (`GET /delta?regions=US,EU`) or "only the frameworks that carry the
  mechanism in an OT zone". The engine does not narrow these on its own; the
  answer is a *view*, and the baseline is unchanged.
* **The sector axis is the engine's own determination (UCM-52).** Sectoral
  applicability (UCM-47) — "a norm that does not govern this sector is not a
  candidate here" — is decided, not asked, exactly as gating decides the technical
  dimension. Building it is not the failure this module guards against: that
  failure is a *silent* narrowing, and this one is anything but.
* **Everything a lens excludes comes back.** The service re-runs the same query
  unfiltered and reports the difference as `set_aside`, with the axis responsible
  (`excluded_axes`). Any lens can therefore be audited — the operator's and the
  engine's alike: what it set aside is on the record next to what it showed.

The zone axis deserves one more note. There is no "zone" field on a control — a
control belongs to a framework, not to a zone — so a zone lens is expressed as the
frameworks that the zone's *declared precedence order* puts first
(`rules.framework_precedence`, UCM-8, versioned data). `zone_lens` reads that
order; it does not invent one. And it takes an explicit `frameworks` count rather
than defaulting to some subset, because a default here would be the engine
quietly deciding what an operator gets to see.
"""

from __future__ import annotations

from qdrant_client import models as qdrant

from app.engine.rules import RuleSet
from app.engine.schemas import ZoneContext
from app.retrieval.index import ControlPayload
from app.retrieval.schemas import FilterAxis, PayloadFilter


def to_qdrant(payload_filter: PayloadFilter | None) -> qdrant.Filter | None:
    """Translate the declared lens into Qdrant's filter language.

    An inactive lens becomes `None` — not an empty `Filter` — so an unfiltered
    retrieval is unfiltered at the wire level too, and cannot be confused with a
    filter that happened to match everything.
    """
    if payload_filter is None or not payload_filter.is_active:
        return None

    conditions: list[qdrant.Condition] = []
    if payload_filter.jurisdictions:
        conditions.append(
            qdrant.FieldCondition(
                key="jurisdiction",
                match=qdrant.MatchAny(any=[j.value for j in payload_filter.jurisdictions]),
            )
        )
    if payload_filter.frameworks:
        conditions.append(
            qdrant.FieldCondition(
                key="framework",
                match=qdrant.MatchAny(any=[f.value for f in payload_filter.frameworks]),
            )
        )
    if payload_filter.mapping_types:
        # `mapping_types` is an array in the payload: a control matches when it
        # takes part in at least one mapping of the requested kind, anywhere in
        # the catalog. "Total somewhere" is a property of the mechanism, which is
        # what is being filtered here.
        conditions.append(
            qdrant.FieldCondition(
                key="mapping_types",
                match=qdrant.MatchAny(any=[m.value for m in payload_filter.mapping_types]),
            )
        )
    if payload_filter.sectors:
        # Sectoral applicability (UCM-47) as a lens. A control applies when its
        # declared scope is *empty* — transversal, the CIS/CSF/IEC case — or when
        # it meets the zone's sectors. Both must survive, so this is a nested OR
        # (`should`, min 1), not a plain `MatchAny`: filtering a transversal
        # control out on `energy ∉ []` would assert it does not apply where it in
        # fact does. What the lens does exclude is a norm whose enumerated scope is
        # disjoint from the zone's — IMO's maritime controls on a gas pipeline.
        conditions.append(
            qdrant.Filter(
                should=[
                    qdrant.IsEmptyCondition(
                        is_empty=qdrant.PayloadField(key="applies_to_sectors")
                    ),
                    qdrant.FieldCondition(
                        key="applies_to_sectors",
                        match=qdrant.MatchAny(any=[s.value for s in payload_filter.sectors]),
                    ),
                ]
            )
        )
    return qdrant.Filter(must=conditions)


def excluded_axes(payload_filter: PayloadFilter, payload: ControlPayload) -> list[FilterAxis]:
    """Which axes of the lens set this control aside. Usually one, sometimes several."""
    axes: list[FilterAxis] = []
    if payload_filter.jurisdictions and payload.jurisdiction not in {
        j.value for j in payload_filter.jurisdictions
    }:
        axes.append(FilterAxis.JURISDICTION)
    if payload_filter.frameworks and payload.framework not in {
        f.value for f in payload_filter.frameworks
    }:
        axes.append(FilterAxis.ZONE)
    if payload_filter.mapping_types and not set(payload.mapping_types) & {
        m.value for m in payload_filter.mapping_types
    }:
        axes.append(FilterAxis.MAPPING_TYPE)
    # Sector excludes only an *enumerated* scope disjoint from the lens: an empty
    # scope is transversal and is never set aside (mirrors `to_qdrant` and UCM-47's
    # `control_applies`), so `energy` does not exclude a control that declares none.
    if (
        payload_filter.sectors
        and payload.applies_to_sectors
        and not set(payload.applies_to_sectors) & {s.value for s in payload_filter.sectors}
    ):
        axes.append(FilterAxis.SECTOR)
    return axes


def zone_lens(zone: ZoneContext, rules: RuleSet, frameworks: int) -> PayloadFilter:
    """The zone axis: the top `frameworks` of the zone's declared precedence order.

    `frameworks` must be stated by the caller. Two, in an OT zone, is
    `[IEC62443, CSF]` — the OT mechanism and the outcome above it — and the CIS
    action, NIS2 and IMO are set aside *and reported*. The engine's own pipeline
    never calls this: it is the operator's exploration tool and the delta demo's.
    """
    if frameworks < 1:
        raise ValueError("a zone lens must keep at least one framework")

    order = rules.framework_precedence[zone.domain]
    kept = order[:frameworks]
    rationale = rules.framework_precedence_rationale.get(zone.domain, "")
    return PayloadFilter(
        frameworks=list(kept),
        zone_domain=zone.domain,
        rationale=(
            f"Lente de zona {zone.zone_id} ({zone.domain.value}): se consultan los "
            f"{frameworks} primeros marcos del orden de precedencia declarado "
            f"({', '.join(f.value for f in kept)}). {rationale} La lente no recorta la línea "
            "base: lo que deja fuera se devuelve como candidato apartado, visible y trazable."
        ),
    )
