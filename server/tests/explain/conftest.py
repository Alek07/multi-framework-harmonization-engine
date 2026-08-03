"""UCM-14 - Fixtures for the explanation tests: a scripted model, real candidates.

Same rule as the parse (UCM-12) and the retrieval (UCM-13) suites: nothing here
talks to a model or opens a connection, so the suite runs on any machine,
offline. `FunctionModel` scripts exactly what the LLM replies — including a
recommendation, an invented candidate and a silence — because those are the
paths that decide whether a presentational layer is really presentational. The
one test that needs the real 7B lives in `test_live_ollama.py`, behind the `llm`
marker.

The candidates the model is asked about are *not* invented for the tests: they
come from the deterministic core's own resolution of profile A and from the RAG
pass over it (`tests/retrieval/conftest.FakeIndex`, which replaces the vectors
and nothing else). What is under test is the shipped agent explaining the
candidates the operator would actually be looking at.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

import pydantic_ai.models
import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.catalog.schemas import Catalog
from app.engine.schemas import CapabilityResolution, ProfileResolution, ZoneContext
from app.explain import service as service_module
from app.explain.agent import ExplainAgent, explain_agent
from app.explain.evidence import CapabilityFacts, facts_for
from app.explain.service import CandidateExplanationService
from app.parse import ollama as ollama_module
from app.retrieval.schemas import CapabilityRetrieval, ProfileRetrieval
from app.retrieval.service import RetrievalService
from tests.retrieval.conftest import FakeIndex

VERIFIED_DIGEST = "845dbda0ea48ed749caafd9e6037047aa19acfcfd82e704d7ca97d631a0b697e"


@dataclass(frozen=True)
class Case:
    """One capability in one zone, exactly as the operator would see it."""

    resolution: CapabilityResolution
    retrieval: CapabilityRetrieval
    zone: ZoneContext
    catalog_version: str

    @property
    def facts(self) -> CapabilityFacts:
        return facts_for(self.resolution, self.retrieval, self.zone)

    @property
    def offered(self) -> list[str]:
        return self.retrieval.offered_control_ids


@pytest.fixture(scope="session")
def retrieval_a(catalog: Catalog, resolution_a: ProfileResolution) -> ProfileRetrieval:
    return RetrievalService(index=FakeIndex(catalog)).retrieve_profile(resolution_a)


@pytest.fixture(scope="session")
def case(resolution_a: ProfileResolution, retrieval_a: ProfileRetrieval) -> Case:
    """A capability with both kinds of candidate: authored mappings and suggestions.

    The interesting assertions are about the difference between the two — what
    each may cite, what each falls back to — so a capability that only had one
    kind would let half the module pass untested.
    """
    for zone in resolution_a.zones:
        retrieved_zone = retrieval_a.zone(zone.zone.zone_id)
        for capability in zone.capabilities:
            retrieval = retrieved_zone.capability(capability.capability.id)
            if capability.options and retrieval.widening:
                return Case(
                    resolution=capability,
                    retrieval=retrieval,
                    zone=zone.zone,
                    catalog_version=retrieval_a.catalog_version,
                )
    raise AssertionError("profile A should resolve some capability with catalog and RAG candidates")


@pytest.fixture(scope="session")
def gap_case(catalog: Catalog, resolution_a: ProfileResolution) -> Case:
    """A capability with no candidate at all: the explicit gap of UCM-13."""
    zone = resolution_a.zones[0]
    capability = CapabilityResolution(
        capability=sorted(catalog.capabilities, key=lambda c: c.id)[0],
        zone_id=zone.zone.zone_id,
        options=[],
        coverage=0.0,
        has_full_mechanism=False,
    )
    empty = RetrievalService(index=FakeIndex(catalog, returns_nothing=True))
    return Case(
        resolution=capability,
        retrieval=empty.retrieve_capability(capability),
        zone=zone.zone,
        catalog_version=catalog.catalog_version,
    )


# --- scripting the model ------------------------------------------------------


def batch_json(entries: list[dict[str, object]]) -> str:
    """An `ExplanationBatch` as the model would return it, valid or not.

    Serialised without validating on purpose: a test has to be able to script an
    answer that omits a candidate, invents one or reads as a recommendation.
    """
    return json.dumps({"explanations": entries}, ensure_ascii=False)


def entry(control_id: str, text: str, basis: list[str]) -> dict[str, object]:
    return {"control_id": control_id, "explanation": text, "basis": basis}


DESCRIPTIVE = "Aparece por su relación declarada con la capacidad."


def well_behaved(case: Case, text: str = DESCRIPTIVE) -> str:
    """A reply that explains every candidate, in order, citing evidence it has.

    The basis is read from the candidate's own allowed set, so the reply is
    grounded by construction — which is what leaves the *failing* replies in the
    other tests unambiguous about what they are failing.
    """
    return batch_json(
        [
            entry(candidate.control_id, text, [candidate.allowed[0].value])
            for candidate in case.facts.candidates
        ]
    )


@contextmanager
def scripted(*replies: str) -> Iterator[tuple[CandidateExplanationService, list[str]]]:
    """The shipped service over a scripted model, and the prompts it was given."""
    with scripted_agent(*replies) as (agent, prompts):
        yield CandidateExplanationService(agent=agent), prompts


@contextmanager
def scripted_agent(*replies: str) -> Iterator[tuple[ExplainAgent, list[str]]]:
    """The shipped agent with a model that returns `replies` in order.

    Yields the agent and the list of prompts it received, so a test can assert on
    what the model was actually told — the fact sheet is part of the contract.
    """
    remaining = list(replies)
    prompts: list[str] = []

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        prompts.append(str(messages[-1].parts[-1].content))  # type: ignore[union-attr]
        reply = remaining.pop(0) if remaining else replies[-1]
        return ModelResponse(parts=[TextPart(reply)])

    agent = explain_agent()
    with agent.override(model=FunctionModel(respond)):
        yield agent, prompts


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
    """Every explanation test runs as if Ollama's digest had already been checked."""
    ollama_module.reset_verification()
    if request.node.get_closest_marker("llm") is not None:
        return

    async def _digest() -> str:
        return VERIFIED_DIGEST

    monkeypatch.setattr(service_module, "verify_model", _digest)
