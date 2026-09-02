"""UCM-53 - The tagger fails open, per control: a run that stumbles degrades to today."""

from __future__ import annotations

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.parse.ollama import ModelUnavailableError
from app.tagging import service as service_module
from app.tagging.agent import tagging_agent
from app.tagging.schemas import TagStatus
from app.tagging.service import FAILED_NOTICE, ControlTaggingService
from tests.tagging.conftest import control, draft_json, premise, scripted_agent


async def test_a_supported_premise_is_proposed() -> None:
    with scripted_agent(draft_json(premise())) as agent:
        proposal = await ControlTaggingService(agent).tag(control())

    assert proposal.status is TagStatus.PROPOSED
    assert [p.premise.value for p in proposal.presupposes] == ["general_purpose_os"]
    assert proposal.rejected == []
    assert proposal.attempts == 1
    assert proposal.control_id == "CTL-CIS-1001"
    assert proposal.notice is None


async def test_no_premise_is_an_answer_not_a_failure() -> None:
    """The expected answer for most of the catalog, and it must not read as an error."""
    with scripted_agent(draft_json()) as agent:
        proposal = await ControlTaggingService(agent).tag(control())

    assert proposal.status is TagStatus.NONE
    assert proposal.presupposes == []
    assert proposal.notice is None


async def test_an_unanchored_premise_leaves_the_control_untagged_but_on_the_record() -> None:
    with scripted_agent(draft_json(premise(quote="correo electrónico corporativo"))) as agent:
        proposal = await ControlTaggingService(agent).tag(control())

    assert proposal.status is TagStatus.NONE
    assert proposal.presupposes == []
    assert len(proposal.rejected) == 1
    assert "no aparece" in proposal.rejected[0].reason


async def test_a_malformed_reply_is_retried_and_the_attempts_are_counted() -> None:
    with scripted_agent("no soy json", draft_json(premise())) as agent:
        proposal = await ControlTaggingService(agent).tag(control())

    assert proposal.status is TagStatus.PROPOSED
    assert proposal.attempts == 2


async def test_a_control_the_model_never_answered_falls_open() -> None:
    def explode(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        raise RuntimeError("connection reset by peer")

    agent = tagging_agent()
    with agent.override(model=FunctionModel(explode)):
        proposal = await ControlTaggingService(agent).tag(control())

    assert proposal.status is TagStatus.UNAVAILABLE
    assert proposal.presupposes == []
    assert proposal.notice == FAILED_NOTICE
    # The reviewer reads this file: the Python exception has no business in it.
    assert "connection reset" not in (proposal.notice or "")


async def test_no_control_is_tagged_without_a_verified_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _refuse() -> str:
        raise ModelUnavailableError("Ollama no responde en http://localhost:11434.")

    monkeypatch.setattr(service_module, "verify_model", _refuse)

    with scripted_agent(draft_json(premise())) as agent:
        proposal = await ControlTaggingService(agent).tag(control())

    assert proposal.status is TagStatus.UNAVAILABLE
    assert proposal.presupposes == []
    assert "Ollama no responde" in (proposal.notice or "")
