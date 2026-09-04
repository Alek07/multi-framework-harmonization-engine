from __future__ import annotations

from collections.abc import Sequence
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.catalog.schemas import (
    Framework,
    FrameworkControl,
    Jurisdiction,
    MappingType,
    Sector,
)
from app.core.wording import say, say_all
from app.engine.schemas import CapabilityGap, GatingOutcome, ZoneContext, ZoneDomain


class RetrievalRelation(str, Enum):
    """What a hit is, relative to what the catalog already offered."""

    # The catalog already maps this control to the capability. Retrieval found it
    # again: a confirmation, worth showing, but not a widening.
    CONFIRMS_MAPPING = "confirms_mapping"
    # The catalog does not map this control to this capability. This is the whole
    # point of the pass — and it is a *suggestion*, pending the human's judgement.
    WIDENS = "widens"


class FilterAxis(str, Enum):
    """The axes a payload filter may act on. `SECTOR` is sectoral applicability
    expressed as a lens; the other three are the retrieval axes proper."""

    JURISDICTION = "jurisdiction"
    ZONE = "zone"
    MAPPING_TYPE = "mapping_type"
    SECTOR = "sector"


class PayloadFilter(BaseModel):
    """A declared lens over the index. Whatever it leaves out is reported back.

    Most axes are the human's use cases (the regional delta, zone-scoped
    exploration) and the engine never applies those on its own. The `sectors` axis
    is different: the engine builds it, because "a norm that does not govern this
    sector is not a candidate here" is a determination, not a silent restriction —
    the same operation gating performs on the technical dimension. It is safe because
    everything set aside comes back in `CapabilityRetrieval.set_aside`, marked with
    the axis that excluded it. The zone axis is derived from the versioned precedence
    rules of the zone's domain, not invented here.
    """

    model_config = ConfigDict(extra="forbid")

    jurisdictions: list[Jurisdiction] | None = None
    frameworks: list[Framework] | None = None
    mapping_types: list[MappingType] | None = None
    sectors: list[Sector] | None = None
    zone_domain: ZoneDomain | None = None
    rationale: str = ""

    @property
    def is_active(self) -> bool:
        return any((self.jurisdictions, self.frameworks, self.mapping_types, self.sectors))

    @property
    def axes(self) -> list[FilterAxis]:
        active: list[FilterAxis] = []
        if self.jurisdictions:
            active.append(FilterAxis.JURISDICTION)
        if self.frameworks:
            active.append(FilterAxis.ZONE)
        if self.mapping_types:
            active.append(FilterAxis.MAPPING_TYPE)
        if self.sectors:
            active.append(FilterAxis.SECTOR)
        return active

    def describe(self) -> str:
        """One line, in Spanish, for the operator and the log.

        Written as a sentence rather than as the filter's literal shape: the set
        notation and the bracketed enum lists this used to print (`jurisdicción ∈
        ['US', 'EU']`) are the query, not what the query *means*, and the person
        reading the trail is being asked to judge whether the lens was fair.
        """
        if not self.is_active:
            return "sin filtro: la recuperación se hace sobre todo el catálogo indexado"
        parts: list[str] = []
        if self.jurisdictions:
            parts.append(f"solo jurisdicción {say_all(self.jurisdictions)}")
        if self.frameworks:
            zone = f", en lectura {say(self.zone_domain)}" if self.zone_domain else ""
            parts.append(f"solo los marcos {say_all(self.frameworks)}{zone}")
        if self.mapping_types:
            parts.append(f"solo mapeos de tipo {say_all(self.mapping_types)}")
        if self.sectors:
            parts.append(
                f"solo normas del ámbito sectorial de la zona ({say_all(self.sectors)}); "
                "las transversales no se apartan"
            )
        return "; ".join(parts)


class SetAsideCandidate(BaseModel):
    """A hit the declared lens excluded. Recorded so the lens is never silent."""

    model_config = ConfigDict(extra="forbid")

    control_id: str
    official_id: str
    framework: Framework
    jurisdiction: Jurisdiction
    score: float
    relation: RetrievalRelation
    # Which axes of the lens excluded it — usually one, sometimes several.
    excluded_by: list[FilterAxis]
    rationale: str


class GatingAnnotation(BaseModel):
    """Why the engine's gating rules out this control *in this zone*.

    Attached to a suggestion the retrieval still shows, so the suggestion cannot
    contradict a gating exclusion in silence. Zone-scoped, not capability-scoped:
    gating decides a control's fate per control and per zone, so the same annotation
    holds wherever the control is suggested. A suggestion carrying this is offered
    *marked*, not hidden, and only the human may adopt it (with the compensatory
    justification gating asks for).
    """

    model_config = ConfigDict(extra="forbid")

    zone_id: str
    outcome: GatingOutcome
    rule_id: str
    rationale: str
    evidence: list[str] = Field(default_factory=list)


class CutReason(str, Enum):
    """Why a retrieved candidate is not among the ones being shown."""

    RANK = "rank"
    FRAMEWORK_CAP = "framework_cap"


class CutPolicy(BaseModel):
    """The rule that decides how many suggestions are shown, and which."""

    model_config = ConfigDict(extra="forbid")

    version: str
    depth: int
    floor: int
    tie_epsilon: float
    ceiling: int
    framework_cap: int

    def describe(self) -> str:
        """One line, in Spanish, for the operator and the log."""
        return (
            f"corte {self.version}: se evalúan {self.depth} candidatos por capacidad, se "
            f"retienen {self.floor} como mínimo y hasta {self.ceiling} mientras sigan a "
            f"menos de {self.tie_epsilon:.2f} del último, con un máximo de "
            f"{self.framework_cap} por marco"
        )


class DroppedCandidate(BaseModel):
    """A retrieved candidate the cut did not retain. Recorded, not deleted."""

    model_config = ConfigDict(extra="forbid")

    control_id: str
    official_id: str
    framework: Framework
    jurisdiction: Jurisdiction
    score: float
    relation: RetrievalRelation
    dropped_by: CutReason
    margin: float
    rationale: str


class RetrievalCut(BaseModel):
    """What the cut left below the line: `retained + dropped == evaluated`."""

    model_config = ConfigDict(extra="forbid")

    policy: CutPolicy
    evaluated: int
    retained: int
    band_width: int
    band_extension: int
    ceiling_reached: bool
    cap_yielded: int = 0
    dropped: int
    near_ties_dropped: int
    not_returned: int
    first_dropped: DroppedCandidate | None = None
    displaced: list[DroppedCandidate] = Field(default_factory=list)
    rationale: str

    @model_validator(mode="after")
    def _the_counts_close(self) -> RetrievalCut:
        """A report whose arithmetic does not close is not evidence of anything."""
        if self.retained + self.dropped != self.evaluated:
            raise ValueError(
                f"the cut reports {self.retained} retained + {self.dropped} dropped, which is "
                f"not the {self.evaluated} candidates it says it evaluated"
            )
        if self.dropped and self.first_dropped is None:
            raise ValueError(
                f"the cut dropped {self.dropped} candidate(s) and names none of them: that is "
                "the silent omission the cut must never produce"
            )
        if self.retained > self.band_width:
            raise ValueError(
                f"the cut retained {self.retained} candidates from a band {self.band_width} "
                "wide: the cap fills the band's slots, it cannot add any"
            )
        return self


class RetrievedControl(BaseModel):
    """A control the index returned for a capability, with why it is being shown.

    `score` is a cosine similarity between the capability's text and the control's
    text. It orders the suggestions for reading and nothing else: it is not a
    coverage weight, it never reaches the deterministic core, and there is
    deliberately no threshold below which a hit is dropped.
    """

    model_config = ConfigDict(extra="forbid")

    control: FrameworkControl
    score: float
    relation: RetrievalRelation
    mapped_capability_ids: list[str] = Field(default_factory=list)
    mapping_types: list[MappingType] = Field(default_factory=list)
    gated_out: GatingAnnotation | None = None
    rationale: str

    @property
    def control_id(self) -> str:
        return self.control.id

    @property
    def framework(self) -> Framework:
        return self.control.framework

    @property
    def jurisdiction(self) -> Jurisdiction:
        return self.control.jurisdiction


# How the suggestion tail is ordered once the cut has decided *which* suggestions
# there are. Versioned like `CUT_POLICY_VERSION`: the operator reads the list top
# down, so the order is part of what the engine says. It sorts; it never removes —
# a suggestion the zone's gating already ruled out reads last and reads marked
# (`gated_out`), never buried or hidden. Applied *after* the cut, so it can move a
# suggestion but never decide whether it survives; that is the cut's call.
ORDERING_VERSION = "v1"


def sink_gated[R: RetrievedControl](retrieved: Sequence[R]) -> list[R]:
    """Gated-out suggestions last, everything else in the rank it arrived with."""
    return [r for r in retrieved if r.gated_out is None] + [
        r for r in retrieved if r.gated_out is not None
    ]


class CapabilityRetrieval(BaseModel):
    """Retrieval for one capability in one zone. Additive by construction."""

    model_config = ConfigDict(extra="forbid")

    capability_id: str
    capability_name: str
    zone_id: str
    catalog_control_ids: list[str] = Field(default_factory=list)
    retrieved: list[RetrievedControl] = Field(default_factory=list)
    set_aside: list[SetAsideCandidate] = Field(default_factory=list)
    cut: RetrievalCut | None = None
    gap: CapabilityGap | None = None
    rationale: str

    @property
    def widening(self) -> list[RetrievedControl]:
        """The suggestions proper: controls the catalog does not map here."""
        return [r for r in self.retrieved if r.relation is RetrievalRelation.WIDENS]

    @property
    def confirmations(self) -> list[RetrievedControl]:
        return [r for r in self.retrieved if r.relation is RetrievalRelation.CONFIRMS_MAPPING]

    @property
    def offered_control_ids(self) -> list[str]:
        """Catalog candidates first, then the suggestions in reading order.

        The catalog half keeps the core's own order, untouched: those are the
        binding options and nothing here may reshuffle them. The suggestion half
        arrives already ordered by `sink_gated` (applied in the service, so every
        reader of `retrieved` sees the same order this returns).
        """
        offered = list(self.catalog_control_ids)
        offered.extend(r.control_id for r in self.widening)
        return offered

    @model_validator(mode="after")
    def _relations_agree_with_the_catalog(self) -> CapabilityRetrieval:
        """A hit cannot both widen and already be mapped — the label must be true."""
        mapped = set(self.catalog_control_ids)
        for hit in self.retrieved:
            widens = hit.relation is RetrievalRelation.WIDENS
            if widens and hit.control_id in mapped:
                raise ValueError(
                    f"{hit.control_id} is labelled 'widens' but the catalog already maps it "
                    f"to {self.capability_id}"
                )
            if not widens and hit.control_id not in mapped:
                raise ValueError(
                    f"{hit.control_id} is labelled 'confirms_mapping' but the catalog does not "
                    f"map it to {self.capability_id}"
                )
        return self

    @model_validator(mode="after")
    def _a_bounded_ranking_declares_its_rule(self) -> CapabilityRetrieval:
        """If the index answered, the cut that bounded the answer must be on record."""
        if self.retrieved and self.cut is None:
            raise ValueError(
                f"{self.capability_id} in {self.zone_id} shows {len(self.retrieved)} retrieved "
                "candidate(s) without declaring the cut that bounded them: a cut without a rule "
                "is a silent omission (invariant 2)"
            )
        return self

    @model_validator(mode="after")
    def _a_gap_means_no_candidate_at_all(self) -> CapabilityRetrieval:
        """The gap flag and the candidate lists cannot tell different stories."""
        if self.gap is not None and self.offered_control_ids:
            raise ValueError(
                f"{self.capability_id} declares a gap while offering "
                f"{self.offered_control_ids}"
            )
        if self.gap is None and not self.offered_control_ids:
            raise ValueError(
                f"{self.capability_id} has no candidate in {self.zone_id} and no declared gap: "
                "that is a silent omission (invariant 2)"
            )
        return self


class RetrievalProvenance(BaseModel):
    """Everything needed to replay this retrieval on another machine.

    The collection name carries the catalog version *and* a digest of the catalog
    the vectors were built from, so a retrieval can never be silently answered by
    stale vectors — and the log says which ones answered it.
    """

    model_config = ConfigDict(extra="forbid")

    embedding_model: str
    embedding_dim: int
    collection: str
    catalog_version: str
    catalog_digest: str
    indexed_controls: int
    text_template_version: str
    top_k: int
    cut_policy: CutPolicy
    # The rule that ordered the suggestion tail, declared beside the one that
    # bounded it. A constant of the code, recorded so a stored answer says which
    # reading order produced it.
    ordering_version: str = ORDERING_VERSION
    payload_filter: PayloadFilter


class ZoneRetrieval(BaseModel):
    """Retrieval for every capability of the catalog in one zone."""

    model_config = ConfigDict(extra="forbid")

    zone: ZoneContext
    capabilities: list[CapabilityRetrieval]

    @property
    def widened_capability_ids(self) -> list[str]:
        return [c.capability_id for c in self.capabilities if c.widening]

    @property
    def suggestions(self) -> int:
        return sum(len(c.widening) for c in self.capabilities)

    @property
    def set_aside(self) -> list[SetAsideCandidate]:
        return [s for c in self.capabilities for s in c.set_aside]

    @property
    def displaced(self) -> list[DroppedCandidate]:
        return [d for c in self.capabilities if c.cut is not None for d in c.cut.displaced]

    @property
    def dropped(self) -> int:
        return sum(c.cut.dropped for c in self.capabilities if c.cut is not None)

    @property
    def gaps(self) -> list[CapabilityGap]:
        return [c.gap for c in self.capabilities if c.gap is not None]

    def capability(self, capability_id: str) -> CapabilityRetrieval:
        for capability in self.capabilities:
            if capability.capability_id == capability_id:
                return capability
        raise KeyError(f"capability not retrieved: {capability_id}")


class ProfileRetrieval(BaseModel):
    """The RAG pass over a whole asset profile, zone by zone.

    Consumed by `POST /candidates` (M3), which shows catalog options and retrieved
    suggestions side by side so the human composes with both — clearly labelled as
    what they are.
    """

    model_config = ConfigDict(extra="forbid")

    profile_id: str
    profile_name: str
    catalog_version: str
    provenance: RetrievalProvenance
    zones: list[ZoneRetrieval]

    @property
    def suggestions(self) -> int:
        return sum(z.suggestions for z in self.zones)

    @property
    def set_aside(self) -> list[SetAsideCandidate]:
        return [s for z in self.zones for s in z.set_aside]

    @property
    def displaced(self) -> list[DroppedCandidate]:
        return [d for z in self.zones for d in z.displaced]

    @property
    def dropped(self) -> int:
        return sum(z.dropped for z in self.zones)

    @property
    def gaps(self) -> list[CapabilityGap]:
        return [g for z in self.zones for g in z.gaps]

    def zone(self, zone_id: str) -> ZoneRetrieval:
        for zone in self.zones:
            if zone.zone.zone_id == zone_id:
                return zone
        raise KeyError(f"zone not retrieved: {zone_id}")
