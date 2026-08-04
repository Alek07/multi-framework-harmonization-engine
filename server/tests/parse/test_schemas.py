"""UCM-12 - The draft schema is a grammar, and the grammar must ask about everything.

Ollama compiles the schema into GBNF: it constrains what the model may emit and it
never reaches the prompt, so `description=` is documentation for us and `required`
is the only instruction the model actually receives from this module.

That distinction was found the hard way. Every field carries a default, so the
schema said `required: []`, and the model answered with `zones`, `conduits` and
`notes` **absent** — not empty. Pydantic applied the defaults and nothing failed:
the operator got a profile with no zones and the log said nothing. A key the model
was never asked about is a silent omission (invariant 2).

These tests need no Ollama. They hold the shape of the question.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from app.parse.schemas import (
    AssetParseRequest,
    AssetProfileDraft,
    ConduitDraft,
    CriticalityDraft,
    ParseNote,
    ParseResult,
    SLVectorDraft,
    TechNatureDraft,
    ZoneDraft,
)

DRAFT_MODELS = [
    AssetProfileDraft,
    ZoneDraft,
    ConduitDraft,
    TechNatureDraft,
    CriticalityDraft,
    SLVectorDraft,
    ParseNote,
]


@pytest.mark.parametrize("model", DRAFT_MODELS, ids=lambda m: m.__name__)
def test_every_field_is_required_of_the_model(model: type[BaseModel]) -> None:
    """Null is an answer the schema accepts; silence is not one it allows."""
    schema = model.model_json_schema()

    assert schema["required"] == list(schema["properties"]), model.__name__


def test_the_fields_that_went_missing_are_named_explicitly() -> None:
    """The regression that started this: three arrays of objects, all omitted."""
    required = AssetProfileDraft.model_json_schema()["required"]

    assert {"zones", "conduits", "notes"} <= set(required)


def test_a_required_key_may_still_be_null() -> None:
    """Forcing the question must not force an answer — that would invent values."""
    draft = AssetProfileDraft.model_validate(
        {
            "name": None,
            "case": None,
            "zones": [
                {
                    "id": "Z-A",
                    "target_sl": None,
                    "nature": {
                        "general_purpose_os": None,
                        "networked": None,
                        "hybrid_it_ot": None,
                        "interactive_users": None,
                        "office_it_surface": None,
                    },
                }
            ],
            "conduits": [],
            "criticality": {
                "physical_consequence": None,
                "scale": None,
                "threat_model": None,
                "consequence_path": None,
                "attack_reference": None,
            },
            "notes": [],
            "unmapped": [],
        }
    )

    assert draft.zones[0].target_sl is None
    assert draft.zones[0].nature.networked is None


def test_python_side_stays_lenient() -> None:
    """`required` governs the grammar, not validation: a partial draft still builds.

    Deliberate. Making the fields required in Python too would turn a model that
    omits one into a 502 for the operator, when the draft it did return is
    reviewable and the missing value is already reported by `missing_required`.
    """
    draft = AssetProfileDraft.model_validate({"name": "Estación", "zones": [{"id": "Z-A"}]})

    assert draft.notes == []
    assert draft.conduits == []
    assert draft.zones[0].nature.networked is None


@pytest.mark.parametrize("model", [AssetParseRequest, ParseResult], ids=lambda m: m.__name__)
def test_the_api_models_keep_their_own_shape(model: type[BaseModel]) -> None:
    """Only what the LLM answers with is forced; the API contract is not."""
    schema = model.model_json_schema()

    assert schema.get("required", []) != list(schema["properties"])
