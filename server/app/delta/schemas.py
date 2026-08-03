"""UCM-15 - Contract of `GET /delta?regions=US,EU`: the same zone, two jurisdictions.

Declared here in full; the body lands in **UCM-17**, which this ticket blocks.
The route validates the query and answers 501, so the shape a client can rely on
is fixed before the logic exists.

What the delta *is*, stated precisely, because it is easy to mistake for a
crosswalk: it is one zone of one profile, read through two declared jurisdiction
lenses (UCM-13's payload filter), with the difference between the two readings
made explicit. Not "what does EU call this US control" — that is translation —
but "compose this zone for a US operator, then for an operator who also answers
to EU obligations, and show what changes".

Two bounds are declared rather than discovered:

* **One zone per call.** The demo answers the question for the demo zone. N zones
  at once is declared future work in the PRD, not an omission to be papered over
  with a loop.
* **A lens sets candidates aside; it never deletes them.** Every reading reports
  what its jurisdiction filter excluded (`set_aside_control_ids`), so "the EU
  reading" is auditable against "the whole index" rather than being a shorter list
  the operator has to take on trust (invariant 2).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.catalog.schemas import Jurisdiction
from app.engine.schemas import ZoneContext
from app.retrieval.schemas import PayloadFilter


class CapabilityRegionView(BaseModel):
    """One capability of the zone, as one jurisdiction's lens sees it."""

    model_config = ConfigDict(extra="forbid")

    region: Jurisdiction
    offered_control_ids: list[str] = Field(default_factory=list)
    # Offered under this lens and under no other in the request: the delta proper.
    only_here_control_ids: list[str] = Field(default_factory=list)
    # What this lens excluded from the same neighbourhood. Apartar no es descartar.
    set_aside_control_ids: list[str] = Field(default_factory=list)
    rationale: str


class CapabilityDelta(BaseModel):
    """The regional difference for one capability in the zone under study."""

    model_config = ConfigDict(extra="forbid")

    capability_id: str
    capability_name: str
    zone_id: str
    # Offered under every region asked for: the part of the baseline that does not
    # depend on where the operator answers.
    common_control_ids: list[str] = Field(default_factory=list)
    regions: list[CapabilityRegionView] = Field(default_factory=list)
    rationale: str


class RegionalDelta(BaseModel):
    """Response of `GET /delta`: one zone, N regional readings, and their difference."""

    model_config = ConfigDict(extra="forbid")

    profile_id: str
    profile_name: str
    zone: ZoneContext
    catalog_version: str
    regions: list[Jurisdiction] = Field(default_factory=list)
    # The declared lens used for each region, in the same order. Recorded so the
    # reading can be reproduced and challenged, not just read.
    lenses: list[PayloadFilter] = Field(default_factory=list)
    capabilities: list[CapabilityDelta] = Field(default_factory=list)
    # Capabilities whose offered set is identical under every region asked for.
    unchanged_capability_ids: list[str] = Field(default_factory=list)
    rationale: str
