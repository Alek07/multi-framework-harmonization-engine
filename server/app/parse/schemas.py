"""Contract of the AI parse: free text -> draft of an `AssetProfile`.

The LLM extracts, it never decides (invariant 1), and the module is shaped by two
consequences. It produces a draft, not a profile: the draft mirrors `AssetProfile`
field by field but makes every value the text may be silent about `None`, so the
model is not forced to invent a missing SL or nature — the operator fills it in
(`completion.py`). And nothing it read may vanish (invariant 2): `notes` justifies
each extracted value with the text fragment behind it, `unmapped` collects every
statement the schema had no place for. The draft is therefore reviewable by
construction, and `ParseResult.review_required` is always true.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.assets.schemas import CaseType, ConsequenceScale
from app.catalog.schemas import Sector

# Ollama compiles this schema into a GBNF grammar; it never enters the prompt
# (measured: `prompt_tokens` is identical with the full schema and a 62-char one).
# The grammar constrains structure only — the `description=` strings below document
# the field for us and do not reach the model; instructions belong in `prompt.py`.
#
# That makes `required` load-bearing. Every field has a default, so the generated
# schema said `required: []` and the model omitted the expensive keys (`zones`,
# `conduits`, `notes` came back absent, Pydantic filling the defaults silently). A
# key the model never answered is a silent omission (invariant 2), so every draft
# model forces all properties into `required` and lets `X | None` carry "not said".


def _require_every_key(schema: dict[str, Any]) -> None:
    """Force the grammar to ask about every field. Null is an answer; silence is not."""
    schema["required"] = list(schema.get("properties", {}))


_ANSWER_EVERY_FIELD = ConfigDict(extra="forbid", json_schema_extra=_require_every_key)


class EvidenceKind(str, Enum):
    """How a value got into the draft. There is no third kind on purpose.

    `INFERRED` is domain reasoning over something the text *does* say ("estación
    de ingeniería" -> `general_purpose_os = true`). A value with no support in the
    text at all is not `ASSUMED`, it is absent: the field stays `None` and the
    operator decides.
    """

    STATED = "stated"
    INFERRED = "inferred"


class ParseNote(BaseModel):
    """Why one field of the draft holds the value it holds."""

    model_config = _ANSWER_EVERY_FIELD

    field: str = Field(
        description="Path of the field in the draft, e.g. 'zones[Z-SCADA].target_sl'."
    )
    kind: EvidenceKind = Field(
        description="'stated' if the text says it literally, 'inferred' if deduced from it."
    )
    evidence: str = Field(
        description="Fragment of the source text, copied verbatim, that supports the value."
    )
    note: str = Field(
        description="One short sentence, in Spanish, explaining the extraction to the operator."
    )


class SLVectorDraft(BaseModel):
    """SL-T per IEC 62443 foundational requirement, each one optional.

    A text that states one FR and not the rest is common; forcing the vector to be
    all-or-nothing would make the parse choose between inventing six values and
    discarding one. Partial vectors are representable so it has to do neither.
    """

    model_config = _ANSWER_EVERY_FIELD

    FR1: int | None = Field(
        default=None, ge=1, le=4, description="Identification and authentication"
    )
    FR2: int | None = Field(default=None, ge=1, le=4, description="Use control")
    FR3: int | None = Field(default=None, ge=1, le=4, description="System integrity")
    FR4: int | None = Field(default=None, ge=1, le=4, description="Data confidentiality")
    FR5: int | None = Field(default=None, ge=1, le=4, description="Restricted data flow")
    FR6: int | None = Field(default=None, ge=1, le=4, description="Timely response to events")
    FR7: int | None = Field(default=None, ge=1, le=4, description="Resource availability")


class TechNatureDraft(BaseModel):
    """Technological nature of one zone — the input gating reads.

    Every field is a tri-state: true, false, or `None` for 'the text does not say'.
    A `False` guessed here would silently remove mechanisms from the baseline,
    which is exactly the failure gating is written to prevent.

    Asked per zone because the answer is per zone: a description that covers an
    embedded controller *and* a Windows operator station settles
    `general_purpose_os` twice, differently, and one asset-wide answer would have
    to lose one of them.
    """

    model_config = _ANSWER_EVERY_FIELD

    general_purpose_os: bool | None = Field(
        default=None,
        description="Zone runs a general-purpose OS (Windows/Linux) rather than firmware.",
    )
    networked: bool | None = Field(default=None, description="Zone is connected to a network.")
    hybrid_it_ot: bool | None = Field(
        default=None, description="Zone itself sits on both the IT and the OT side."
    )
    interactive_users: bool | None = Field(
        default=None, description="Human users log into this zone interactively."
    )
    office_it_surface: bool | None = Field(
        default=None,
        description="Zone exposes office IT surface: mail, browsing, USB, office suite.",
    )


class ZoneDraft(BaseModel):
    """A security zone as the text describes it (IEC 62443)."""

    model_config = _ANSWER_EVERY_FIELD

    id: str = Field(
        description="Stable identifier in upper case, prefix 'Z-', derived from the zone's name."
    )
    target_sl: int | None = Field(
        default=None,
        ge=1,
        le=4,
        description="Target security level 1-4. Null unless the text states or implies one.",
    )
    nature: TechNatureDraft = Field(
        default_factory=TechNatureDraft,
        description="Technological nature of this zone, answered for this zone alone.",
    )
    purdue: str | None = Field(
        default=None, description="Purdue level as written: 'L0'...'L4', or 'IDMZ'."
    )
    role: str | None = Field(
        default=None, description="Role of the zone, e.g. 'crown_jewel' for a safety system."
    )
    sectors: list[Sector] = Field(
        default_factory=list,
        description=(
            "Sectors this zone operates in, only when the text distinguishes them from the "
            "asset's — a maritime berth zone on an energy asset is ['maritime']. Empty otherwise."
        ),
    )
    position: str | None = Field(
        default=None, description="Position relative to the IDMZ: 'north_of_idmz'/'south_of_idmz'."
    )
    sl_vector: SLVectorDraft | None = Field(
        default=None, description="Per-FR levels, only if the text gives them."
    )
    safety_out_of_scope: bool | None = Field(
        default=None,
        description="True if the text keeps the safety function (SIS) out of the baseline's scope.",
    )
    reference: str | None = Field(
        default=None, description="Incident or standard cited for this zone, e.g. 'TRITON/TRISIS'."
    )


class ConduitDraft(BaseModel):
    """A conduit between zones (IEC 62443), including the IDMZ crossing."""

    model_config = _ANSWER_EVERY_FIELD

    id: str = Field(description="Stable identifier in upper case, prefix 'C-'.")
    endpoints: list[str] = Field(
        default_factory=list,
        description="Zone ids or named endpoints the conduit joins, in the text's order.",
    )
    control: str | None = Field(
        default=None,
        description="How the text says the conduit is controlled, as a lower_snake_case phrase.",
    )


class CriticalityDraft(BaseModel):
    """Physical consequence of a compromise — what prioritisation weighs."""

    model_config = _ANSWER_EVERY_FIELD

    physical_consequence: str | None = Field(
        default=None,
        description="Physical consequence in lower_snake_case, e.g. 'overpressure_rupture_leak'.",
    )
    scale: ConsequenceScale | None = Field(
        default=None, description="Severity of that consequence. Null unless the text supports one."
    )
    threat_model: str | None = Field(
        default=None, description="Threat model cited, e.g. 'ATTACK_for_ICS'."
    )
    consequence_path: str | None = Field(
        default=None,
        description="How the compromise reaches the physical process, e.g. 'indirect_pivot_to_ot'.",
    )
    attack_reference: str | None = Field(
        default=None, description="Attack or incident cited as reference."
    )


class AssetProfileDraft(BaseModel):
    """What the model returns: an `AssetProfile` with every uncertain field empty.

    This is the type Pydantic AI validates the model's output against, so a
    malformed answer is a retry (with the validation error fed back), never a
    silent half-parse.
    """

    model_config = _ANSWER_EVERY_FIELD

    name: str | None = Field(
        default=None, description="Short name of the asset, as the text calls it."
    )
    case: CaseType | None = Field(
        default=None,
        description=(
            "PURE_OT if the asset lives only in OT; HYBRID_IT_OT if it straddles IT and OT."
        ),
    )
    sectors: list[Sector] = Field(
        default_factory=list,
        description=(
            "Critical-infrastructure sectors the asset operates in. Empty unless the text names "
            "them; a gas pipeline is ['energy'], a port ['maritime', 'energy']. Never guessed — "
            "the operator completes it."
        ),
    )
    zones: list[ZoneDraft] = Field(
        default_factory=list, description="One entry per security zone the text describes."
    )
    conduits: list[ConduitDraft] = Field(
        default_factory=list, description="One entry per conduit or connection the text describes."
    )
    criticality: CriticalityDraft = Field(
        default_factory=CriticalityDraft, description="Physical consequence of a compromise."
    )
    notes: list[ParseNote] = Field(
        default_factory=list,
        description="One note per non-null field extracted, with the text fragment behind it.",
    )
    unmapped: list[str] = Field(
        default_factory=list,
        description=(
            "Every statement in the text that no field of this schema can hold, copied verbatim. "
            "Leaving something out of both the draft and this list is the one forbidden outcome."
        ),
    )


class AssetParseRequest(BaseModel):
    """Body of `POST /asset/parse`: the operator's own description.

    `profile_id` is optional and it is a *key*, not an observation: given, it is
    used verbatim so a second parse of a corrected description lands on the same
    identifier and the audit log reads as one asset. Left out, it is derived from
    the name the model extracted (`completion.profile_id_for`).
    """

    model_config = ConfigDict(extra="forbid")

    description: str = Field(
        min_length=1,
        description="Descripción libre del activo, tal y como la escribe el operador.",
    )
    profile_id: str | None = Field(
        default=None,
        description="Identificador a asignar al perfil. Si se omite, se deriva del nombre.",
    )


class ParseProvenance(BaseModel):
    """Everything needed to replay this parse on another machine.

    The digest is the one that Ollama reported for the model it actually served,
    not the one that was asked for: a tag is mutable and pins nothing on its own.
    `prompt_version` is here for the same reason — the prompt is an input of the
    result, so changing it is a versioned act, not an edit.
    """

    model_config = ConfigDict(extra="forbid")

    model: str
    model_digest: str
    prompt_version: str
    temperature: float
    seed: int
    top_p: float
    num_predict: int
    # Model requests spent on this parse: 1, plus one per Pydantic validation
    # retry. A number above 1 is not a defect, it is the retry loop working.
    attempts: int
    # SHA-256 of the source text, so the log can prove which words produced this
    # draft without storing the operator's paragraph twice.
    source_sha256: str


class ParseResult(BaseModel):
    """The parse's output: a draft, its gaps, and how it was produced.

    `review_required` is a constant, not a computed flag. Even a draft with no
    missing field is a *proposal*: the profile the core runs on exists only once a
    human has confirmed it (`completion.to_profile`).
    """

    model_config = ConfigDict(extra="forbid")

    profile_id: str
    draft: AssetProfileDraft
    # Dotted paths the operator must fill before `AssetProfile` can be built.
    # Computed deterministically from the draft — never by the model.
    missing_required: list[str]
    provenance: ParseProvenance
    review_required: bool = True
