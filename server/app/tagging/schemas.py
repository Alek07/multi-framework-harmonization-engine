"""What a control presupposes of a zone: the model's proposal, and its review.

**Nothing in this package runs in the request path** — this is catalog authorship.
A script (`scripts/tag_presuppositions.py`) walks the catalog once, asks the model
what each control needs, screens the answers deterministically, and writes a
proposal file; a human corrects it and merges what survives into the catalog
sources, and from then on the engine reads a fact frozen in Git.

That ordering is the point. The blindness being fixed is structural in a
bi-encoder — "no hay workstation" and "workstation" land in nearly the same place
in one 768-dim vector — and the reading that fixes it is the *same* for every
asset, zone and run. Doing it once, under review, buys a deterministic answer
forever without putting a 7B on the path of a baseline.

So the chain is: **the model proposes, a deterministic guard screens, the human
authorises, and only then does a rule decide.**
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.catalog.schemas import Framework, Premise, Presupposition


# Same reasoning as the parse draft (`app/parse/schemas.py`): Ollama compiles this
# schema into a GBNF grammar, and a field with a default lets the model omit the
# key entirely rather than answer it. Every property is forced into `required` so
# silence stops being an available answer.
def _require_every_key(schema: dict[str, Any]) -> None:
    """Force the grammar to ask about every field. Null is an answer; silence is not."""
    schema["required"] = list(schema.get("properties", {}))


_ANSWER_EVERY_FIELD = ConfigDict(extra="forbid", json_schema_extra=_require_every_key)


class TagStatus(str, Enum):
    """Why a control's entry looks the way it does.

    `PROPOSED` and `NONE` are both answers — the second one says the model read
    the control and found no premise, which is the expected answer for most of
    the catalog and must not be confused with the model never having been asked.
    """

    PROPOSED = "proposed"
    NONE = "none"
    UNAVAILABLE = "unavailable"


class PremiseDraft(BaseModel):
    """One premise the model proposes, with the words it read it from.

    `quote` is not decoration: it is what makes the proposal checkable without a
    second model. The guard requires the fragment to appear in the control's own
    title or description, so a premise the model inferred from its training
    rather than from the text in front of it can be dropped mechanically instead
    of argued about.
    """

    model_config = _ANSWER_EVERY_FIELD

    premise: Premise
    expected: bool
    note: str
    quote: str


class ControlTagDraft(BaseModel):
    """The model's whole answer for one control. An empty list is a real answer."""

    model_config = _ANSWER_EVERY_FIELD

    presupposes: list[PremiseDraft]


class RejectedPremise(BaseModel):
    """A premise the guard refused, kept so the reviewer can overrule the guard."""

    model_config = ConfigDict(extra="forbid")

    premise: str
    expected: bool
    note: str
    quote: str
    reason: str


class ControlProposal(BaseModel):
    """What is proposed for one control, and what was thrown away getting there."""

    model_config = ConfigDict(extra="forbid")

    control_id: str
    official_id: str
    framework: Framework
    title: str
    paraphrased_description: str
    presupposes: list[Presupposition] = Field(default_factory=list)
    rejected: list[RejectedPremise] = Field(default_factory=list)
    status: TagStatus
    notice: str | None = None
    attempts: int = 0


class TaggingProvenance(BaseModel):
    """The run's inputs, on the same footing as the catalog itself (invariant 3)."""

    model_config = ConfigDict(extra="forbid")

    model: str
    model_digest: str | None
    prompt_version: str
    temperature: float
    seed: int
    top_p: float
    num_predict: int
    catalog_version: str
    catalog_digest: str


class TaggingRun(BaseModel):
    """The proposal file the human reviews. It is never read by the engine."""

    model_config = ConfigDict(extra="forbid")

    provenance: TaggingProvenance
    proposals: list[ControlProposal]
    counts: dict[str, int] = Field(default_factory=dict)
