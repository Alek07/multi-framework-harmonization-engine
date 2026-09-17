"""Contract of the candidate explanations: prose, and nothing else.

This is the third and least powerful AI pass: it only writes *why a candidate is
on screen*. It is P1 and strictly presentational — it does not rank, select,
filter or reach the deterministic core (invariant 1). The models below make
breaking that a shape that cannot be constructed:

* **The explained view is a bijection onto the offered candidates, in order.**
  `CapabilityExplanations` restates `offered_control_ids` and a validator requires
  the explanations to be those same IDs in that same sequence. Reordering would be
  ranking, which is why the check is on the *list* rather than on the set.
* **There is no number to influence.** `CandidateExplanation` has no score,
  weight, rank or tier field: coverage is arithmetic over authored mappings, and
  prose is not evidence of equivalence.
* **Every candidate always carries readable text.** When the model is off,
  unreachable, or writes a verdict, `text` falls back to the deterministic
  rationale, `status` says which happened, and the candidate is untouched.
* **What the model may cite is a closed list.** `basis` is drawn from
  `EvidenceKey`, and the service only accepts the keys that candidate actually has
  (`app/explain/evidence.py`); anything else is caught, withheld and reported.

Nothing here writes to the audit log — the LLM is not an actor. `digest` exists so
the operator's decision entry can name the exact prose it was reading.
"""

from __future__ import annotations

import hashlib
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.catalog.schemas import Framework, Jurisdiction

# A candidate on screen without a reason next to it is the thing this module
# exists to prevent, so the text is never allowed to be empty.
NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class CandidateOrigin(str, Enum):
    """Where the candidate came from. It is not a quality order, it is provenance."""

    # Authored mapping in the versioned catalog: the deterministic core offered it.
    CATALOG = "catalog"
    # Suggested by the RAG pass: a neighbour in embedding space, not a mapping.
    RETRIEVAL = "retrieval"


class EvidenceKey(str, Enum):
    """The only facts an explanation may lean on. Closed by design.

    Each key names something already written down — in the catalog, in the core's
    resolution or in the retrieval — so a reader can go and check it. The model
    receives, per candidate, the subset that candidate actually has; citing
    anything else is a groundedness failure and is treated as one.
    """

    # The catalog maps this control to this capability, and how.
    CATALOG_MAPPING = "catalog_mapping"
    MAPPING_TYPE = "mapping_type"
    COVERAGE_WEIGHT = "coverage_weight"
    MAPPING_PROVENANCE = "mapping_provenance"
    # The control does its declared work on *other* capabilities (RAG candidates).
    NEIGHBOURING_MAPPING = "neighbouring_mapping"
    # Cosine similarity between the capability's text and the control's. Only ever
    # a reading order; it never becomes coverage.
    SIMILARITY = "similarity"
    FRAMEWORK = "framework"
    JURISDICTION = "jurisdiction"
    STRENGTH = "strength"
    CONTROL_TEXT = "control_text"
    # `superseded` / `contested`: what the core already said about this candidate.
    CANDIDATE_STATUS = "candidate_status"
    # Zone reading (domain, SL-target, safety relevance) the core derived.
    ZONE_CONTEXT = "zone_context"


class ExplanationStatus(str, Enum):
    """Where the text on screen came from. Never a silent substitution."""

    # The model wrote it, and it survived the presentational guard.
    GENERATED = "generated"
    # The model wrote something that reads as a recommendation, or cited evidence
    # the candidate does not have. The prose is withheld — the candidate is not.
    WITHHELD = "withheld"
    # No usable answer: Ollama unreachable, wrong digest, invalid output, or the
    # model simply did not return this candidate.
    UNAVAILABLE = "unavailable"
    # The layer is switched off by configuration (`EXPLAIN_ENABLED`). P1 is
    # optional by definition, and being off is a declared state, not a failure.
    DISABLED = "disabled"


class CandidateExplanation(BaseModel):
    """Why one candidate is on screen, in one paragraph the operator can read.

    Note what this model cannot express: there is no score, no rank, no priority
    and no verdict field. It carries the identity of the candidate, prose, and the
    provenance of that prose.
    """

    model_config = ConfigDict(extra="forbid")

    control_id: str
    official_id: str
    framework: Framework
    jurisdiction: Jurisdiction
    origin: CandidateOrigin
    # What the operator reads. Model prose when `status` is `generated`, the
    # engine's own deterministic rationale in every other case.
    text: NonBlank
    status: ExplanationStatus
    # Empty unless the model wrote the text: the deterministic fallback is not a
    # citation of evidence, it *is* the evidence.
    basis: list[EvidenceKey] = Field(default_factory=list)
    # Why the operator is reading the engine's text rather than the model's.
    # Written so that "nothing was generated" and "something was generated and
    # rejected" are never the same silence.
    notice: str | None = None

    @property
    def from_model(self) -> bool:
        return self.status is ExplanationStatus.GENERATED

    @model_validator(mode="after")
    def _only_generated_text_cites_evidence(self) -> CandidateExplanation:
        """`basis` describes the model's reasoning, so it belongs to model prose only."""
        if self.basis and self.status is not ExplanationStatus.GENERATED:
            raise ValueError(
                f"{self.control_id} is '{self.status.value}' but cites "
                f"{[b.value for b in self.basis]}: only generated prose carries a basis"
            )
        if self.status is ExplanationStatus.GENERATED and not self.basis:
            raise ValueError(
                f"{self.control_id} is 'generated' with no cited evidence: an explanation that "
                "leans on nothing checkable is exactly what this layer may not show"
            )
        if self.status is ExplanationStatus.GENERATED and self.notice is not None:
            raise ValueError(
                f"{self.control_id} shows the model's own text and also explains why it does not"
            )
        if self.status is ExplanationStatus.WITHHELD and not self.notice:
            raise ValueError(
                f"{self.control_id} withholds the model's text without saying so: withholding "
                "in silence is the failure this status exists to make visible"
            )
        return self


class ExplanationProvenance(BaseModel):
    """How this batch of prose was produced — or why it was not.

    Same shape as `ParseProvenance` and for the same reason: the decoding
    parameters are inputs of the text, so two runs that show different words must
    be explainable by something written down here.
    """

    model_config = ConfigDict(extra="forbid")

    model: str
    # Null when the model was never reached: the digest is what Ollama reported
    # for the tag it actually served, and an unverified run has none to report.
    model_digest: str | None = None
    prompt_version: str
    # The fact sheet is as much an input of the prose as the instructions are:
    # the same candidates rendered differently produce different sentences. It is
    # versioned alongside the prompt for the same reason retrieval versions its
    # own text template (`RetrievalProvenance.text_template_version`).
    sheet_template_version: str
    temperature: float
    seed: int
    top_p: float
    num_predict: int
    # Model requests spent on this capability, retries included. 0 means the
    # request never left: disabled, unreachable, or nothing to explain.
    attempts: int = 0
    catalog_version: str
    # Control IDs the model returned that were not offered for this capability —
    # an invented candidate, or one repeated twice. They never reach the screen,
    # and they are written down here rather than dropped without trace.
    ignored_control_ids: list[str] = Field(default_factory=list)
    # Why this batch carries no model prose at all: switched off, model
    # unreachable, output rejected. The candidates are on screen regardless.
    notice: str | None = None


class CapabilityExplanations(BaseModel):
    """The explained view of one capability in one zone. Additive, ordered, inert.

    `presentational` is a `Literal[True]` for the same reason `CapabilityGating`
    pins `required`: it is the contract of the ticket written into the type, not a
    flag anybody may flip.
    """

    model_config = ConfigDict(extra="forbid")

    capability_id: str
    capability_name: str
    zone_id: str
    # Copied verbatim from `CapabilityRetrieval.offered_control_ids`: catalog
    # candidates first, in the core's order, then the retrieved suggestions.
    offered_control_ids: list[str] = Field(default_factory=list)
    explanations: list[CandidateExplanation] = Field(default_factory=list)
    provenance: ExplanationProvenance
    presentational: Literal[True] = True

    @property
    def generated(self) -> list[CandidateExplanation]:
        return [e for e in self.explanations if e.status is ExplanationStatus.GENERATED]

    @property
    def withheld(self) -> list[CandidateExplanation]:
        return [e for e in self.explanations if e.status is ExplanationStatus.WITHHELD]

    @property
    def digest(self) -> str:
        """SHA-256 of exactly what was shown, candidate by candidate.

        The composition entry the human signs can carry this digest, so the log
        says which words were on screen when the choice was made without storing the
        prose of a model that decided nothing.
        """
        payload = "\n".join(
            f"{e.control_id}|{e.status.value}|{e.text}" for e in self.explanations
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def explanation(self, control_id: str) -> CandidateExplanation:
        for explanation in self.explanations:
            if explanation.control_id == control_id:
                return explanation
        raise KeyError(f"candidate not explained: {control_id}")

    @model_validator(mode="after")
    def _every_candidate_explained_exactly_once_and_in_order(self) -> CapabilityExplanations:
        """The bijection. Dropping, adding or reordering a candidate is unbuildable.

        Order matters as much as membership: the candidates arrive in the order
        the deterministic core and the retrieval produced them, and a layer that
        may only explain has no business changing what the operator sees first.
        """
        explained = [e.control_id for e in self.explanations]
        if explained != self.offered_control_ids:
            raise ValueError(
                f"{self.capability_id} in {self.zone_id} offers {self.offered_control_ids} and "
                f"explains {explained}: the explanation layer is presentational and may not add, "
                "drop or reorder a candidate"
            )
        return self


class ZoneExplanations(BaseModel):
    """Explained candidates for every capability of one zone, in the zone's order."""

    model_config = ConfigDict(extra="forbid")

    zone_id: str
    capabilities: list[CapabilityExplanations] = Field(default_factory=list)
    presentational: Literal[True] = True

    @property
    def generated(self) -> int:
        return sum(len(c.generated) for c in self.capabilities)

    @property
    def withheld(self) -> int:
        return sum(len(c.withheld) for c in self.capabilities)

    def capability(self, capability_id: str) -> CapabilityExplanations:
        for capability in self.capabilities:
            if capability.capability_id == capability_id:
                return capability
        raise KeyError(f"capability not explained: {capability_id}")


# --- what the model itself returns --------------------------------------------


class ExplanationDraft(BaseModel):
    """One explanation as the model writes it, before it is screened.

    The field descriptions below are part of the prompt: Ollama serves this schema
    as `response_format`, so llama.cpp constrains decoding to it. It buys the shape;
    the presentational rules are checked by `guard.py`.
    """

    model_config = ConfigDict(extra="forbid")

    control_id: str = Field(
        description="The candidate's control_id, copied verbatim from the candidate list."
    )
    explanation: str = Field(
        description=(
            "Why this candidate is shown for this capability. Spanish, at most 45 words, "
            "descriptive only: never say which candidate is better, which to choose, "
            "which to discard or whether one applies."
        )
    )
    basis: list[EvidenceKey] = Field(
        default_factory=list,
        description=(
            "The facts this explanation rests on, taken only from the 'evidencia citable' "
            "list of that candidate. Never cite a key that is not listed for it."
        ),
    )


class ExplanationBatch(BaseModel):
    """Every candidate of one capability, explained in a single request."""

    model_config = ConfigDict(extra="forbid")

    explanations: list[ExplanationDraft] = Field(
        default_factory=list,
        description="One entry per candidate given, in the same order, none added, none omitted.",
    )
