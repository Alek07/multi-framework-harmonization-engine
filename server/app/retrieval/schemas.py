"""UCM-13 - Contract of the RAG pass: what retrieval adds, and what it may not do.

Retrieval is the second AI pass of M2, and like the first one (UCM-12) it neither
decides nor ranks nor filters the baseline (invariant 1). Its single job is to
*widen* the set of options the human sees, and the whole contract below is shaped
by the one invariant the ticket makes measurable:

    **RAG only widens coverage. It never restricts it, and never in silence.**

Three properties of these models are what make that claim checkable rather than
merely asserted:

* **The catalog's candidates are carried through verbatim.** Every
  `CapabilityRetrieval` restates the control IDs step 1 of the core already
  offered (`catalog_control_ids`), and `offered_control_ids` is their union with
  whatever was retrieved. A retrieval that dropped one would fail its own
  validator, not just a test.
* **A retrieved control is never a mapping.** It arrives with a similarity score
  and a `relation`, never with a `coverage_weight`: the catalog's typed mappings
  are authored (`official_crosswalk` / `author_judgment`) and an embedding
  distance is not evidence of equivalence. Coverage, gating and prioritisation
  therefore keep reading the deterministic core, untouched by this module — what
  the operator gets is *more options to choose from*, not a different arithmetic.
* **A declared lens sets candidates aside; it does not delete them.** When a
  payload filter is applied (jurisdiction, zone, mapping type), everything it
  excluded comes back in `set_aside`, with the axis that excluded it. A filter
  whose leftovers were invisible would be exactly the silent restriction the
  invariant forbids.

A capability that ends with no candidate at all — neither from the catalog nor
from retrieval — becomes an explicit `CapabilityGap` (`NO_CANDIDATE`), the same
type the deterministic core declares. The requirement stays; only the mechanism
is missing.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.catalog.schemas import (
    Framework,
    FrameworkControl,
    Jurisdiction,
    MappingType,
)
from app.engine.schemas import CapabilityGap, ZoneContext, ZoneDomain


class RetrievalRelation(str, Enum):
    """What a hit is, relative to what the catalog already offered."""

    # The catalog already maps this control to the capability. Retrieval found it
    # again: a confirmation, worth showing, but not a widening.
    CONFIRMS_MAPPING = "confirms_mapping"
    # The catalog does not map this control to this capability. This is the whole
    # point of the pass — and it is a *suggestion*, pending the human's judgement.
    WIDENS = "widens"


class FilterAxis(str, Enum):
    """The three axes a payload filter may act on (the ticket's own list)."""

    JURISDICTION = "jurisdiction"
    ZONE = "zone"
    MAPPING_TYPE = "mapping_type"


class PayloadFilter(BaseModel):
    """A declared lens over the index. Opt-in, and never applied by default.

    The engine's own pipeline retrieves **unfiltered**: narrowing the retrieval on
    its own initiative is the failure mode this ticket exists to prevent. The
    filter is here for the human's use cases — the regional delta of
    `GET /delta?regions=US,EU`, and zone-scoped exploration — and whatever it
    leaves out is reported back (`CapabilityRetrieval.set_aside`).

    The zone axis is not invented here: `frameworks` is derived from the versioned
    precedence rules of the zone's domain (`for_zone`), so a zone lens is a
    reading of declared data, not a preference hidden in code.
    """

    model_config = ConfigDict(extra="forbid")

    jurisdictions: list[Jurisdiction] | None = None
    frameworks: list[Framework] | None = None
    mapping_types: list[MappingType] | None = None
    # Recorded for the audit trail when `frameworks` came from a zone's domain:
    # it is the difference between "the operator asked for IEC+CSF" and "this is
    # the OT reading of the precedence rules".
    zone_domain: ZoneDomain | None = None
    rationale: str = ""

    @property
    def is_active(self) -> bool:
        return any((self.jurisdictions, self.frameworks, self.mapping_types))

    @property
    def axes(self) -> list[FilterAxis]:
        active: list[FilterAxis] = []
        if self.jurisdictions:
            active.append(FilterAxis.JURISDICTION)
        if self.frameworks:
            active.append(FilterAxis.ZONE)
        if self.mapping_types:
            active.append(FilterAxis.MAPPING_TYPE)
        return active

    def describe(self) -> str:
        """One line, in Spanish, for the operator and the log."""
        if not self.is_active:
            return "sin filtro de payload: la recuperación se hace sobre todo el índice"
        parts: list[str] = []
        if self.jurisdictions:
            parts.append(f"jurisdicción ∈ {[j.value for j in self.jurisdictions]}")
        if self.frameworks:
            zone = f" (lectura {self.zone_domain.value})" if self.zone_domain else ""
            parts.append(f"marco ∈ {[f.value for f in self.frameworks]}{zone}")
        if self.mapping_types:
            parts.append(f"tipo de mapeo ∈ {[m.value for m in self.mapping_types]}")
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
    # Where this control does its declared work in the catalog. A widening
    # suggestion is far easier to judge when the operator can see that the control
    # is, say, the CIS action already mapped to a neighbouring capability.
    mapped_capability_ids: list[str] = Field(default_factory=list)
    mapping_types: list[MappingType] = Field(default_factory=list)
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


class CapabilityRetrieval(BaseModel):
    """Retrieval for one capability in one zone. Additive by construction."""

    model_config = ConfigDict(extra="forbid")

    capability_id: str
    capability_name: str
    zone_id: str
    # What step 1 of the deterministic core already offered here, carried through
    # untouched. Retrieval adds to this list; it can never shorten it.
    catalog_control_ids: list[str] = Field(default_factory=list)
    retrieved: list[RetrievedControl] = Field(default_factory=list)
    set_aside: list[SetAsideCandidate] = Field(default_factory=list)
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
        """Catalog candidates plus retrieved ones, in a stable order."""
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
    """Everything needed to replay this retrieval on another machine (UCM-22).

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
    def gaps(self) -> list[CapabilityGap]:
        return [g for z in self.zones for g in z.gaps]

    def zone(self, zone_id: str) -> ZoneRetrieval:
        for zone in self.zones:
            if zone.zone.zone_id == zone_id:
                return zone
        raise KeyError(f"zone not retrieved: {zone_id}")
