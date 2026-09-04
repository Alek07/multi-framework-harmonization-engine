"""Catalog data model (Pydantic <-> JSON schemas).

These models are, at once, the schema of the versioned catalog
(`data/catalog/*.json`), the API contract, and the LLM output type. The catalog
is read-only and frozen/versioned in Git (reproducibility). Code identifiers are
in English; catalog *content* (name/description) stays in Spanish by convention.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.wording import strength_words


class Framework(str, Enum):
    CSF = "CSF"
    IEC62443 = "IEC62443"
    CIS = "CIS"
    NIS2 = "NIS2"
    IMO = "IMO"
    CIRCIA = "CIRCIA"
    TSA = "TSA"


class Jurisdiction(str, Enum):
    US = "US"
    EU = "EU"
    INTL = "INTL"
    INTL_MARITIME = "INTL-MARITIME"


class Sector(str, Enum):
    """The sector an asset belongs to, and the sectors a norm governs.

    A neutral, own taxonomy — not NIS2's Annexes nor the US 16 verbatim, since
    those do not align one to one; a neutral enum each framework maps onto makes
    that misalignment demonstrable (a gas pipeline is *Energy* under NIS2 but
    *Transportation Systems* under TSA). A closed set both the asset and the
    catalog draw from, so the engine can intersect the two.

    Both sides carry a list: a control names the sectors it governs
    (`applies_to_sectors`), an asset the sectors it operates in
    (`AssetProfile.sectors`), narrowable per zone (`Zone.sectors`). A norm applies
    to a zone when their sectors intersect; an empty control list is transversal
    (see `FrameworkControl`).
    """

    ENERGY = "energy"
    WATER = "water"
    MARITIME = "maritime"
    TRANSPORT = "transport"
    HEALTH = "health"
    DIGITAL_INFRASTRUCTURE = "digital_infrastructure"
    BANKING_FINANCE = "banking_finance"
    PUBLIC_ADMINISTRATION = "public_administration"
    MANUFACTURING = "manufacturing"
    CHEMICAL = "chemical"
    FOOD = "food"


class MappingType(str, Enum):
    TOTAL = "total"
    PARTIAL = "partial"
    COMPENSATORY = "compensatory"
    CONTEXTUAL = "contextual"


class ProvenanceSource(str, Enum):
    OFFICIAL_CROSSWALK = "official_crosswalk"
    AUTHOR_JUDGMENT = "author_judgment"


class ControlType(str, Enum):
    TECHNICAL = "technical"
    LEGAL = "legal"


class StrengthKind(str, Enum):
    """What kind of demand a control makes — the axis its `level` is measured on.

    Each framework grades its controls on its own scale, and the engine reads two
    of them: the CIS Implementation Group as ready-made IT prioritisation, and the
    SL at which an IEC SR becomes required. Naming the scale keeps those two
    readable without parsing prose.
    """

    IG = "ig"
    SL_BASELINE = "sl_baseline"
    OUTCOME = "outcome"
    LEGAL = "legal"
    GUIDELINE = "guideline"


# The vocabulary the catalog used before v0.3.0, when `strength` was free text.
# Declared as a table rather than parsed with a regex: the shipped v0.1.0 and
# v0.2.0 catalogs must keep loading with the meaning they were authored with, and
# a frozen lookup says exactly what each of those fifteen strings meant. It is a
# migration aid, not an extension point — new catalog versions write the object.
_LEGACY_STRENGTHS: dict[str, tuple[StrengthKind, int | None, str]] = {
    "IG1": (StrengthKind.IG, 1, ""),
    "IG2": (StrengthKind.IG, 2, ""),
    "IG3": (StrengthKind.IG, 3, ""),
    "resultado": (StrengthKind.OUTCOME, None, ""),
    "base SL1": (StrengthKind.SL_BASELINE, 1, ""),
    "base SL1; REs a SL2-3": (StrengthKind.SL_BASELINE, 1, "con refuerzos (RE) a SL2-3"),
    "base SL1; REs a SL3": (StrengthKind.SL_BASELINE, 1, "con refuerzos (RE) a SL3"),
    "requerido a SL2-3": (StrengthKind.SL_BASELINE, 2, ""),
    "requerido a SL3": (StrengthKind.SL_BASELINE, 3, ""),
    "reforzado a SL3": (
        StrengthKind.SL_BASELINE,
        3,
        "refuerzo de un requisito ya presente en niveles inferiores",
    ),
    "clave a SL3 (anti-TRITON)": (StrengthKind.SL_BASELINE, 3, "clave frente al escenario TRITON"),
    "obligación (SMS)": (StrengthKind.LEGAL, None, "dentro del SMS"),
    "directriz (SMS)": (StrengthKind.GUIDELINE, None, "dentro del SMS"),
    "obligación legal": (StrengthKind.LEGAL, None, ""),
    "obligación legal (24h/72h/1 mes)": (
        StrengthKind.LEGAL,
        None,
        "aviso temprano 24 h, notificación 72 h, informe final 1 mes",
    ),
}

_LEVELLED = {StrengthKind.IG: (1, 3), StrengthKind.SL_BASELINE: (1, 4)}


class ControlStrength(BaseModel):
    """What a control demands, on the scale of the framework that publishes it.

    Structured rather than free text because the engine reads it: prioritisation
    reuses the CIS IG, and the SL of an IEC SR is what makes a control mandatory
    for a zone. Parsing that back out of Spanish prose put a regex between the
    catalog and a Tier 0 decision; `kind` and `level` remove it. `note` carries
    what the scale cannot — deadlines, enhancements — and is presentational.
    """

    model_config = ConfigDict(extra="forbid")

    kind: StrengthKind
    level: int | None = None
    note: str = ""

    @model_validator(mode="before")
    @classmethod
    def _accept_legacy_string(cls, value: Any) -> Any:
        """Read the pre-v0.3.0 free-text form, so shipped catalogs still load."""
        if not isinstance(value, str):
            return value
        legacy = _LEGACY_STRENGTHS.get(value.strip())
        if legacy is None:
            raise ValueError(f"Unknown legacy strength: {value!r}")
        kind, level, note = legacy
        return {"kind": kind, "level": level, "note": note}

    @model_validator(mode="after")
    def _check_level(self) -> ControlStrength:
        bounds = _LEVELLED.get(self.kind)
        if bounds is None:
            if self.level is not None:
                raise ValueError(
                    f"{self.kind.value} is not a levelled scale, got level={self.level}"
                )
            return self
        low, high = bounds
        if self.level is None or not low <= self.level <= high:
            raise ValueError(f"{self.kind.value} needs a level in {low}-{high}, got {self.level}")
        return self

    @property
    def label(self) -> str:
        """The Spanish phrase an operator reads. Presentational, never decides."""
        return strength_words(self.kind.value, self.level, self.note)


class Premise(str, Enum):
    """A condition of the zone that a control may presuppose.

    The values are the field names of `TechNature` (`app/assets/schemas.py`): the
    premises the operator already answers, zone by zone, when reviewing the parsed
    profile. Spelled out here rather than imported because the asset schemas import
    *this* module; `tests/catalog/test_presuppositions.py` asserts the two stay in
    step, so the vocabulary is closed by a test instead of a comment.
    """

    GENERAL_PURPOSE_OS = "general_purpose_os"
    NETWORKED = "networked"
    HYBRID_IT_OT = "hybrid_it_ot"
    INTERACTIVE_USERS = "interactive_users"
    OFFICE_IT_SURFACE = "office_it_surface"


class Presupposition(BaseModel):
    """What a control needs to be true of a zone for it to mean anything.

    A control that says "deploy an anti-malware agent on workstations" presupposes
    a general-purpose OS. This is the *fact*, declared on the control; what to do
    about it is a gating rule's business, not this model's — the catalog states,
    the rules decide.

    `expected` is the value the zone must carry for the control to make sense:
    almost always `True`, and `False` for the rarer control that exists only
    because a zone is *not* something. `note` is the sentence the operator reads
    when the mechanism leaves their baseline, so it is required.
    """

    model_config = ConfigDict(extra="forbid")

    premise: Premise
    expected: bool = True
    note: str = Field(min_length=1)


class Capability(BaseModel):
    """Neutral capability: a security outcome decoupled from any framework."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    description: str
    csf_seed_category: str
    ot_refinements: list[str] = Field(default_factory=list)


class FrameworkControl(BaseModel):
    """A framework control: official ID and title + paraphrased description."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str
    framework: Framework
    official_id: str
    title: str
    paraphrased_description: str
    jurisdiction: Jurisdiction
    strength: ControlStrength
    control_type: ControlType = Field(alias="type")
    # The sectors this control governs — its declared scope of applicability.
    # Empty is not the same as enumerated: an empty list means *transversal* (the
    # cross-sector technical frameworks CIS, CSF, IEC 62443), while a non-empty
    # list claims the norm governs *only* those sectors, so an asset outside them
    # becomes a justified exclusion — never a silent drop. Defaults to empty, so
    # catalogs before v0.4.0 keep loading unchanged.
    applies_to_sectors: list[Sector] = Field(default_factory=list)

    # What this control needs the zone to be, for it to mean anything. Empty is
    # the default and says only that no premise has been declared — not that the
    # control is universal. **Absence never excludes**: a control with no
    # presupposition is retained in every zone, which is what lets catalogs up to
    # v0.4.0 keep loading unchanged.
    presupposes: list[Presupposition] = Field(default_factory=list)

    @model_validator(mode="after")
    def _each_premise_is_declared_once(self) -> FrameworkControl:
        """One control cannot hold two readings of the same premise."""
        declared = [p.premise.value for p in self.presupposes]
        twice = sorted({name for name in declared if declared.count(name) > 1})
        if twice:
            raise ValueError(f"{self.id}: premise declared more than once: {', '.join(twice)}")
        return self

    @property
    def transversal(self) -> bool:
        """No declared scope: the control applies to every sector."""
        return not self.applies_to_sectors


class Provenance(BaseModel):
    """Provenance of a mapping, with its jurisdiction (traces origin, never decides)."""

    model_config = ConfigDict(extra="forbid")

    source: ProvenanceSource
    jurisdiction: Jurisdiction
    note: str = ""


class Mapping(BaseModel):
    """Typed control <-> capability mapping, with coverage weight and provenance."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    capability_id: str
    control_id: str
    mapping_type: MappingType = Field(alias="type")
    coverage_weight: float = Field(ge=0.0, le=1.0)
    provenance: Provenance


class Catalog(BaseModel):
    """Full versioned catalog. Validates its referential integrity on load.

    A catalog may live in one file or be split across one file per framework
    (`sources` in the manifest, merged by the loader before this model ever sees
    it). Either way what is validated here is the *whole* catalog: a source file
    on its own maps onto capabilities declared in the manifest and is not
    independently valid. The model is identical either way, on purpose — the
    split is an authoring convenience and nothing downstream may be able to tell.
    """

    model_config = ConfigDict(extra="ignore")

    catalog_version: str
    scope_note: str | None = None
    ip_note: str | None = None
    limitations: list[str] = Field(default_factory=list)
    # `sources` is deliberately *not* a field here. It says which files the
    # catalog was assembled from, which is a fact about the repository and not
    # about the catalog: the loader reads it from the raw JSON and this model
    # never sees it. Carrying it would put it inside `model_dump_json()`, and
    # that is what `app/retrieval/index.py` fingerprints — a renamed file, or a
    # catalog split into more pieces with identical content, would invalidate a
    # perfectly valid index and make every already-shipped version hash
    # differently than it did.
    capabilities: list[Capability] = Field(default_factory=list)
    controls: list[FrameworkControl] = Field(default_factory=list)
    mappings: list[Mapping] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_referential_integrity(self) -> Catalog:
        # The three lists default to empty so a manifest can hold none of them
        # itself, which leaves a mistyped key loading as "nothing here". Nothing
        # downstream would fail on an empty catalog — the engine would simply
        # find no capability to require, which is the silent omission the whole
        # design forbids. So emptiness is an error, stated here once.
        if not self.capabilities:
            raise ValueError("Catalog without capabilities")
        if not self.controls:
            raise ValueError("Catalog without controls")

        dupe_caps = _duplicates(c.id for c in self.capabilities)
        if dupe_caps:
            raise ValueError(f"Duplicate capability IDs: {sorted(dupe_caps)}")
        dupe_ctls = _duplicates(c.id for c in self.controls)
        if dupe_ctls:
            raise ValueError(f"Duplicate control IDs: {sorted(dupe_ctls)}")

        cap_ids = self.capability_ids
        ctl_ids = self.control_ids
        for i, m in enumerate(self.mappings):
            if m.capability_id not in cap_ids:
                raise ValueError(
                    f"mapping[{i}] references a non-existent capability: {m.capability_id}"
                )
            if m.control_id not in ctl_ids:
                raise ValueError(
                    f"mapping[{i}] references a non-existent control: {m.control_id}"
                )
        return self

    @property
    def capability_ids(self) -> set[str]:
        return {c.id for c in self.capabilities}

    @property
    def control_ids(self) -> set[str]:
        return {c.id for c in self.controls}

    def mappings_for(self, capability_id: str) -> list[Mapping]:
        return [m for m in self.mappings if m.capability_id == capability_id]

    def orphan_capabilities(self) -> set[str]:
        """Capabilities with no mapped control (unintended gap)."""
        mapped = {m.capability_id for m in self.mappings}
        return self.capability_ids - mapped

    def unused_controls(self) -> set[str]:
        """Controls not referenced by any mapping."""
        used = {m.control_id for m in self.mappings}
        return self.control_ids - used


def _duplicates(items) -> set[str]:
    seen: set[str] = set()
    dupes: set[str] = set()
    for it in items:
        if it in seen:
            dupes.add(it)
        seen.add(it)
    return dupes
