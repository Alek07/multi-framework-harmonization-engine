"""UCM-15/UCM-17/UCM-50 - Contract of `POST /delta`: one zone, N regional readings.

The shape was fixed in UCM-15 before the logic existed; UCM-17 filled it in;
UCM-50 makes the comparison symmetric and adds a legal-regime lens without
changing what a client already sending the old body gets back.

What the delta *is*, stated precisely, because it is easy to mistake for a
crosswalk: it is one zone of one profile, read once per region, with the
difference between the readings made explicit. Not "what does EU call this US
control" — that is translation — but "compose this zone for a US operator, then
for an operator who also answers to EU obligations, and show what changes".

**Two axes the human chooses, and the engine obeys** (invariant: the engine never
applies a lens on its own initiative):

* `mode` — how the readings relate.
  * `cumulative` (the default, UCM-3): reading *i* offers everything the regions
    up to *i* offer, so "+EU" is the US reading *plus* the European overlay, never
    a parallel catalog in which a European operator has no CIS and no CSF. This is
    still the right answer for an operator subject to *both* regimes.
  * `symmetric`: each reading offers only its own region's contribution over the
    common ground, and the difference is reported in **both** directions — what US
    demands that EU does not, *and* what EU demands that US does not. This is the
    half UCM-50 restored: the cumulative reading could never let the first region
    report what it alone requires.
* `regime` — what enters the axis of comparison.
  * `all` (the default): jurisdiction is the axis — a control counts for a region
    when its jurisdiction is that region.
  * `legal`: only `legal` controls of the compared regions differentiate; the
    common technical ground (CIS, CSF, IEC 62443) stays fixed in every reading and
    is credited to no region. This makes the comparison law-against-law instead of
    law-against-voluntary-guidance — the very confusion that produced the original
    finding, since CIS/CSF carry a US jurisdiction but are voluntary guidance.

Bounds declared rather than discovered:

* **One zone per call.** The demo answers the question for the demo zone. N zones
  at once is declared future work, not an omission papered over with a loop.
* **A lens sets candidates aside; it never deletes them.** Every reading reports
  what its own lens left out (`set_aside_control_ids`) — the controls of the other
  region (symmetric) or of a region still to come (cumulative). A filter whose
  leftovers were invisible would be exactly the silent restriction invariant 2
  forbids.
* **The delta reads authored mappings, not embedding distances.** The question
  "what does EU require that US does not" is answered by the versioned catalog and
  the deterministic core, so it is reproducible with Qdrant and Ollama off. A
  similarity score has no business answering a question about legal obligation.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.assets.schemas import AssetProfile
from app.catalog.schemas import ControlStrength, Framework, Jurisdiction, MappingType
from app.engine.schemas import CapabilityGap, ZoneContext
from app.retrieval.schemas import PayloadFilter


class DeltaMode(str, Enum):
    """How the regional readings relate to one another (UCM-50)."""

    # Reading i offers every region up to i: "+EU" is the US reading plus EU.
    CUMULATIVE = "cumulative"
    # Each reading offers only its own region over the common ground; the delta is
    # reported in both directions.
    SYMMETRIC = "symmetric"


class DeltaRegime(str, Enum):
    """What enters the axis of comparison (UCM-50)."""

    # Jurisdiction is the axis. The common ground is the jurisdictions not compared.
    ALL = "all"
    # Only `legal` controls of the compared regions differentiate; every technical
    # control stays fixed as common ground, whatever its jurisdiction.
    LEGAL = "legal"


class DeltaRequest(BaseModel):
    """Body of `POST /delta`: which asset, which zone, and which regions in order.

    The profile is named the same way `POST /candidates` and
    `POST /baseline/compose` name it — inline or by id, never both — and that
    symmetry is the point of the shape. The delta answers "compose this zone for
    a US operator, then for one who also answers to EU obligations": *this* zone,
    of *this* asset. An endpoint that could only be asked about the profiles
    frozen in the repository could not be asked about the asset the operator has
    just composed, which is the question the engine exists to answer.

    `profile_id` remains, and not as a courtesy: the frozen profiles are the
    inputs the core was validated against and the ones the evaluation measures
    (UCM-18), so the Swagger demo — the declared plan B — still reaches the whole
    comparison without pasting a profile into the request.
    """

    model_config = ConfigDict(extra="forbid")

    regions: list[str] = Field(
        min_length=1,
        description=(
            "Jurisdicciones a comparar en orden, p. ej. ['US','EU'] o ['US,EU']. Mínimo dos, "
            "sin repetir. Las lecturas son acumulativas: la segunda es la primera más esa "
            "región."
        ),
    )
    profile: AssetProfile | None = Field(
        default=None,
        description="Perfil revisado por el operador. Excluyente con 'profile_id'.",
    )
    profile_id: str | None = Field(
        default=None,
        description="Identificador de un perfil congelado en el repositorio, p. ej. 'PROFILE-A'.",
    )
    zone_id: str = Field(
        min_length=1,
        description=(
            "Zona del perfil sobre la que se calcula el delta. Una sola: N zonas por consulta "
            "son trabajo futuro declarado."
        ),
    )
    mode: DeltaMode = Field(
        default=DeltaMode.CUMULATIVE,
        description=(
            "Cómo se relacionan las lecturas. 'cumulative': «+EU» es la lectura anterior más esa "
            "región (correcto para un operador sujeto a ambos regímenes). 'symmetric': cada "
            "lectura ofrece solo su región y la diferencia se reporta en ambos sentidos."
        ),
    )
    regime: DeltaRegime = Field(
        default=DeltaRegime.ALL,
        description=(
            "Qué controles diferencian la comparación. 'all': la jurisdicción. 'legal': solo los "
            "controles legales; el terreno técnico común (CIS/CSF/IEC 62443) queda fijo. Así la "
            "comparación es ley-contra-ley y no mezcla marcos voluntarios con obligaciones."
        ),
    )


class RegionalRequirement(BaseModel):
    """A control one reading offers and the reading before it did not.

    This is the delta itself, control by control, and the field that matters most
    is `changes_coverage`. In this catalog every NIS2 mapping is `contextual` with
    a low weight — a legal obligation over a capability the common ground already
    covers technically — so what "+EU" adds is *exigencia*, not coverage. Reporting
    only the identical coverage number would make the delta look empty when it is
    not; reporting only the extra control would suggest a technical gap that does
    not exist. Both facts travel together.
    """

    model_config = ConfigDict(extra="forbid")

    control_id: str
    official_id: str
    framework: Framework
    jurisdiction: Jurisdiction
    mapping_type: MappingType
    coverage_weight: float
    # What the control demands, as the catalog declares it: an outcome, a CIS
    # implementation group, an SL, or a statutory obligation with its deadlines.
    strength: ControlStrength
    # Which reading brought it in.
    added_by: Jurisdiction
    # Whether it moves the capability's coverage, or only what is owed.
    changes_coverage: bool
    rationale: str


class CapabilityRegionView(BaseModel):
    """One capability of the zone, as one reading sees it."""

    model_config = ConfigDict(extra="forbid")

    region: Jurisdiction
    # "US", "+EU": the reading's own name. The `+` says it is cumulative.
    label: str
    # The jurisdictions this reading offers, common ground included.
    jurisdictions: list[Jurisdiction] = Field(default_factory=list)
    offered_control_ids: list[str] = Field(default_factory=list)
    # What this reading contributes that no other one does. In `cumulative` mode
    # this is always empty on the first reading — it is the starting point, and
    # everything it offers the later readings offer too. In `symmetric` mode every
    # reading, the first included, reports its own exclusive contribution: that is
    # the direction the cumulative reading could not express (UCM-50).
    only_here_control_ids: list[str] = Field(default_factory=list)
    # Candidates the catalog maps here that this reading's lens left out — controls
    # of the other region (symmetric) or of a region still to come (cumulative).
    # Apartar no es descartar.
    set_aside_control_ids: list[str] = Field(default_factory=list)
    frameworks: list[Framework] = Field(default_factory=list)
    # Computed by the deterministic core over this reading's options, not here.
    coverage: float = 0.0
    has_full_mechanism: bool = False
    # Declared when this reading offers no candidate at all for the capability.
    gap: CapabilityGap | None = None
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
    added: list[RegionalRequirement] = Field(default_factory=list)
    # The readings differ at all, and whether the difference reaches coverage.
    changed: bool = False
    changes_coverage: bool = False
    rationale: str


class RegimeApplicability(BaseModel):
    """Whether a legal framework governs this zone at all (UCM-50, on UCM-47).

    The engine does not choose the comparison, but it *does* determine
    applicability and say so with its reason: TSA governs the transport sector, so
    it applies to a pipeline and not to a hospital; CIRCIA is transversal and
    applies always. Reported for every legal framework of the compared regions,
    applicable or not, so the human chooses the comparison already knowing which
    regimes are even in play — and so a non-applicable regime is a visible datum,
    not a silence.
    """

    model_config = ConfigDict(extra="forbid")

    framework: Framework
    jurisdiction: Jurisdiction
    # The sectors the framework governs across its controls; empty when it carries
    # a transversal control, which is what makes it apply regardless of sector.
    governs_sectors: list[str] = Field(default_factory=list)
    applicable: bool
    rationale: str


class RegionalDelta(BaseModel):
    """Response of `POST /delta`: one zone, N regional readings, and their difference."""

    model_config = ConfigDict(extra="forbid")

    profile_id: str
    profile_name: str
    zone: ZoneContext
    catalog_version: str
    rules_version: str
    # How the readings related and what differentiated them — echoed back so the
    # response is self-describing and a reading can be reproduced from it.
    mode: DeltaMode = DeltaMode.CUMULATIVE
    regime: DeltaRegime = DeltaRegime.ALL
    regions: list[Jurisdiction] = Field(default_factory=list)
    # Jurisdictions present in every reading because they are not under
    # comparison: the common ground the question is asked over.
    common_jurisdictions: list[Jurisdiction] = Field(default_factory=list)
    # The declared lens of each reading, in the same order. Recorded so a reading
    # can be reproduced and challenged, not just read.
    lenses: list[PayloadFilter] = Field(default_factory=list)
    capabilities: list[CapabilityDelta] = Field(default_factory=list)
    changed_capability_ids: list[str] = Field(default_factory=list)
    # Capabilities whose offered set is identical under every region asked for.
    unchanged_capability_ids: list[str] = Field(default_factory=list)
    # Capabilities whose *gap* depends on the region: one reading declares one and
    # another does not, or some reading offers no candidate at all.
    #
    # Deliberately not "every capability with a gap". The deterministic core also
    # declares gaps for partial or residual coverage, and those come from the
    # common ground: they are identical under every reading, so calling them
    # regional would be a false finding. They are still reported, per reading, in
    # `CapabilityRegionView.gap`. This list is reported even when empty — that the
    # jurisdiction never opens or closes a gap in this zone is a result, not an
    # absence of one.
    regional_gap_capability_ids: list[str] = Field(default_factory=list)
    # Which legal regimes of the compared regions govern this zone, with the
    # engine's reason. Determined, not chosen (UCM-47/UCM-50): reglas deciden
    # aplicabilidad, humano elige la comparación.
    regime_applicability: list[RegimeApplicability] = Field(default_factory=list)
    rationale: str

    def capability(self, capability_id: str) -> CapabilityDelta:
        for capability in self.capabilities:
            if capability.capability_id == capability_id:
                return capability
        raise KeyError(f"capability not in the delta: {capability_id}")
