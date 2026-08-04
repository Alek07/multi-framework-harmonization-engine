"""UCM-7 - Catalog data model (Pydantic <-> JSON schemas).

These models are, at once, the schema of the versioned catalog
(`data/catalog/*.json`), the API contract, and the LLM output type. The catalog
is read-only and frozen/versioned in Git (reproducibility). Code identifiers are
in English; catalog *content* (name/description) stays in Spanish by convention.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Framework(str, Enum):
    CSF = "CSF"
    IEC62443 = "IEC62443"
    CIS = "CIS"
    NIS2 = "NIS2"
    IMO = "IMO"


class Jurisdiction(str, Enum):
    US = "US"
    EU = "EU"
    INTL = "INTL"
    INTL_MARITIME = "INTL-MARITIME"


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
    strength: str
    control_type: ControlType = Field(alias="type")


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
