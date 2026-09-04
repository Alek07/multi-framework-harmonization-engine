"""Fixtures for the parse tests: a scripted model instead of Ollama.

`FunctionModel` scripts exactly what the LLM replies (a malformed one included),
so the retry loop, provenance and refusal-to-invent are asserted deterministically
and the suite runs with no GPU, Ollama or network. The scripted model is swapped
into the *real* agent (`agent.override`), so what is under test is the shipped
agent. The one live test lives in `test_live_ollama.py`, behind the `llm` marker.
`verify_model` is stubbed because it is a network call; the guarantee that no draft
is produced without a verified digest is asserted in `test_ollama.py`.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager

import pydantic_ai.models
import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.parse import ollama as ollama_module
from app.parse import service as service_module
from app.parse.agent import ParseAgent, parse_agent

VERIFIED_DIGEST = "845dbda0ea48ed749caafd9e6037047aa19acfcfd82e704d7ca97d631a0b697e"

# A description that states some things and stays silent about others on purpose:
# no target SL, no physical consequence, nothing about office IT surface. How the
# parse handles the silence is the point.
DESCRIPTION_ES = (
    "Estación de ingeniería de gasoducto sobre Windows 10, en nivel 3 al norte de "
    "la IDMZ. Descarga lógica a los PLC del corredor a través de la IDMZ y el "
    "proveedor entra por un jump host con MFA. El mantenimiento se hace los martes."
)

# A serious consequence, rated nowhere. Reading a severity out of it is judgement,
# and judgement is the operator's (see the `scale` note in `app/parse/prompt.py`).
DESCRIPTION_UNRATED_CONSEQUENCE = (
    "Estación de bombeo. Un PLC empotrado controla las bombas. Un fallo puede "
    "provocar una sobrepresión y la rotura de la línea."
)


def draft_json(**overrides: object) -> str:
    """A draft as the model would return it, minus what a test changes.

    Serialised without validating: a test has to be able to script an answer the
    schema rejects, which is exactly what the retry loop is for.
    """
    payload: dict[str, object] = {
        "name": "Estación de ingeniería de gasoducto",
        "case": "HYBRID_IT_OT",
        "zones": [
            {
                "id": "Z-ENG-STATION",
                "purdue": "L3",
                "position": "north_of_idmz",
                "nature": {
                    "general_purpose_os": True,
                    "networked": True,
                    "hybrid_it_ot": True,
                    "interactive_users": True,
                },
            }
        ],
        "conduits": [
            {
                "id": "C-IDMZ",
                "endpoints": ["Z-ENG-STATION", "IDMZ"],
                "control": "mediated_logic_download",
            }
        ],
        "criticality": {},
        "notes": [
            {
                "field": "zones[Z-ENG-STATION].nature.general_purpose_os",
                "kind": "stated",
                "evidence": "sobre Windows 10",
                "note": "El texto indica un sistema operativo de propósito general.",
            }
        ],
        "unmapped": ["El mantenimiento se hace los martes."],
    }
    payload.update(overrides)
    return json.dumps(payload, ensure_ascii=False)


@contextmanager
def scripted_agent(*replies: str) -> Iterator[ParseAgent]:
    """The real agent with a model that returns `replies` in order, one per request.

    Passing more than one reply scripts the retry loop: the first is rejected by
    Pydantic, the validation error goes back to the model, and the next reply is
    the answer. The last reply is repeated if the agent asks again.
    """
    remaining = list(replies)

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        reply = remaining.pop(0) if remaining else replies[-1]
        return ModelResponse(parts=[TextPart(reply)])

    agent = parse_agent()
    with agent.override(model=FunctionModel(respond)):
        yield agent


@pytest.fixture(autouse=True)
def _only_scripted_models(request: pytest.FixtureRequest) -> Iterator[None]:
    """No test reaches a real provider unless it is the one marked `llm`.

    Pydantic AI's own switch rather than a mock: it catches a request made from
    anywhere, including code a later refactor adds behind the service.
    """
    allowed = request.node.get_closest_marker("llm") is not None
    previous = pydantic_ai.models.ALLOW_MODEL_REQUESTS
    pydantic_ai.models.ALLOW_MODEL_REQUESTS = allowed
    yield
    pydantic_ai.models.ALLOW_MODEL_REQUESTS = previous


@pytest.fixture(autouse=True)
def _verified_model(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every parse test runs as if Ollama's digest had already been checked.

    Except the `llm` ones: there the digest check is part of what is being tested.
    """
    ollama_module.reset_verification()
    if request.node.get_closest_marker("llm") is not None:
        return

    async def _digest() -> str:
        return VERIFIED_DIGEST

    monkeypatch.setattr(service_module, "verify_model", _digest)
