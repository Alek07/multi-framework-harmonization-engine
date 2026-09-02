"""UCM-53 - Fixtures for the tagging tests: a scripted model instead of Ollama.

Same discipline as the parse fixtures. The scripted model is swapped into the
*real* agent (`agent.override`) so what is under test is the agent this POC
ships, with its output type and its retry budget, and no test can reach a
provider. The run against the real model lives in `test_live_ollama.py`, behind
the `llm` marker.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pydantic_ai.models
import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.catalog.schemas import ControlStrength, Framework, FrameworkControl, Jurisdiction
from app.parse import ollama as ollama_module
from app.tagging import service as service_module
from app.tagging.agent import TaggingAgent, tagging_agent

VERIFIED_DIGEST = "845dbda0ea48ed749caafd9e6037047aa19acfcfd82e704d7ca97d631a0b697e"


def control(**overrides: Any) -> FrameworkControl:
    """A catalog control whose text carries a quotable premise."""
    payload: dict[str, Any] = {
        "id": "CTL-CIS-1001",
        "framework": Framework.CIS,
        "official_id": "10.1",
        "title": "Deploy and Maintain Anti-Malware Software",
        "paraphrased_description": (
            "Desplegar y mantener software antimalware en los equipos de la organización."
        ),
        "jurisdiction": Jurisdiction.US,
        "strength": ControlStrength(kind="ig", level=1),
        "type": "technical",
    }
    payload.update(overrides)
    return FrameworkControl.model_validate(payload)


def draft_json(*premises: dict[str, Any]) -> str:
    """A model reply, built without validation so a malformed one can be scripted."""
    return json.dumps({"presupposes": list(premises)}, ensure_ascii=False)


def premise(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "premise": "general_purpose_os",
        "expected": True,
        "note": "Requiere un sistema operativo donde instalar y mantener el agente.",
        "quote": "software antimalware en los equipos",
    }
    payload.update(overrides)
    return payload


@contextmanager
def scripted_agent(*replies: str) -> Iterator[TaggingAgent]:
    """The real agent with a model that returns `replies` in order, one per request."""
    remaining = list(replies)

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        reply = remaining.pop(0) if remaining else replies[-1]
        return ModelResponse(parts=[TextPart(reply)])

    agent = tagging_agent()
    with agent.override(model=FunctionModel(respond)):
        yield agent


@pytest.fixture(autouse=True)
def _only_scripted_models(request: pytest.FixtureRequest) -> Iterator[None]:
    """No test reaches a real provider unless it is the one marked `llm`."""
    allowed = request.node.get_closest_marker("llm") is not None
    previous = pydantic_ai.models.ALLOW_MODEL_REQUESTS
    pydantic_ai.models.ALLOW_MODEL_REQUESTS = allowed
    yield
    pydantic_ai.models.ALLOW_MODEL_REQUESTS = previous


@pytest.fixture(autouse=True)
def _verified_model(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every tagging test runs as if Ollama's digest had already been checked."""
    ollama_module.reset_verification()
    if request.node.get_closest_marker("llm") is not None:
        return

    async def _digest() -> str:
        return VERIFIED_DIGEST

    monkeypatch.setattr(service_module, "verify_model", _digest)
