"""Fixtures for the closed surface: the shipped app, and no network at all.

Tests run offline with no Ollama, Qdrant or embedding model: only the LLM
replies, the vectors and the digest check are replaced, by the same stand-ins the
unit suites use, so the shipped code path runs end to end. Overrides go through
`app.dependency_overrides`; the process-wide agents (`lru_cache`) are overridden
on an `ExitStack` the fixture unwinds, so a scripted model never leaks into the
next test.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import ExitStack
from typing import Any

import pydantic_ai.models
import pytest
from fastapi.testclient import TestClient
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.api.deps import candidates_service, parse_service
from app.candidates.service import CandidatesService
from app.catalog.schemas import Catalog
from app.core.config import settings
from app.engine.schemas import ProfileGating, ProfileResolution
from app.explain import service as explain_service_module
from app.explain.agent import explain_agent
from app.explain.evidence import facts_for
from app.explain.service import CandidateExplanationService
from app.main import app
from app.parse import ollama as ollama_module
from app.parse import service as parse_service_module
from app.parse.agent import parse_agent
from app.parse.service import AssetParseService
from app.retrieval.index import IndexHit, IndexUnavailableError
from app.retrieval.service import RetrievalService
from tests.explain.conftest import batch_json, entry
from tests.parse.conftest import VERIFIED_DIGEST, draft_json
from tests.retrieval.conftest import FakeIndex

PREFIX = settings.API_V1_PREFIX

DESCRIPTIVE = "Aparece por su relación declarada con la capacidad."


class DownIndex(FakeIndex):
    """A catalog index that cannot be reached. The deterministic result must survive."""

    def search(self, text: str, limit: int, query_filter: Any = None) -> list[IndexHit]:
        raise IndexUnavailableError(
            "No se pudo preparar la colección 'catalog_v0_1_0_test' en http://localhost:6333"
        )


def scripted_model(*replies: str) -> FunctionModel:
    """A model that returns `replies` in order and repeats the last one."""
    remaining = list(replies)

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        reply = remaining.pop(0) if remaining else replies[-1]
        return ModelResponse(parts=[TextPart(reply)])

    return FunctionModel(respond)


@pytest.fixture(autouse=True)
def _no_real_models() -> Iterator[None]:
    """Not one request leaves this process, from anywhere behind the routers."""
    previous = pydantic_ai.models.ALLOW_MODEL_REQUESTS
    pydantic_ai.models.ALLOW_MODEL_REQUESTS = False
    yield
    pydantic_ai.models.ALLOW_MODEL_REQUESTS = previous


@pytest.fixture(autouse=True)
def _verified_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every request runs as if Ollama's digest had already been checked."""
    ollama_module.reset_verification()

    async def _digest() -> str:
        return VERIFIED_DIGEST

    monkeypatch.setattr(parse_service_module, "verify_model", _digest)
    monkeypatch.setattr(explain_service_module, "verify_model", _digest)


@pytest.fixture(autouse=True)
def overrides() -> Iterator[ExitStack]:
    """Everything a test swaps in — dependency or scripted model — is undone here."""
    with ExitStack() as stack:
        yield stack
        for dependency in (parse_service, candidates_service):
            app.dependency_overrides.pop(dependency, None)


# --- POST /asset/parse --------------------------------------------------------


@pytest.fixture
def scripted_parse(overrides: ExitStack) -> Callable[..., None]:
    """Install a parse service whose model returns exactly what the test scripts."""

    def install(*replies: str) -> None:
        agent = parse_agent()
        overrides.enter_context(agent.override(model=scripted_model(*replies)))
        app.dependency_overrides[parse_service] = lambda: AssetParseService(agent=agent)

    return install


@pytest.fixture
def parsing(scripted_parse: Callable[..., None]) -> None:
    """The common case: the model returns a well-formed draft with gaps left in it."""
    scripted_parse(draft_json())


# --- POST /candidates ---------------------------------------------------------


def _install_candidates(service: CandidatesService) -> CandidatesService:
    app.dependency_overrides[candidates_service] = lambda: service
    return service


@pytest.fixture
def offline_candidates(catalog: Catalog) -> CandidatesService:
    """The real service over the real core, with the vectors replaced and no LLM."""
    return _install_candidates(
        CandidatesService(retrieval=RetrievalService(index=FakeIndex(catalog)))
    )


@pytest.fixture
def candidates_without_index(catalog: Catalog) -> CandidatesService:
    """The same service on a machine where Qdrant is down."""
    return _install_candidates(
        CandidatesService(retrieval=RetrievalService(index=DownIndex(catalog)))
    )


def _first_explainable(
    catalog: Catalog, resolution: ProfileResolution, gating: ProfileGating
) -> tuple[str, str, list[str], str]:
    """A capability with both kinds of candidate, and the reply that explains them.

    The reply is built from the actual candidates the service offers (resolution
    plus the RAG pass), in order, because `CapabilityExplanations` refuses any
    other set; the gating goes in too, exactly as `CandidatesService` passes it,
    or the fixture's order would differ from the endpoint's.
    """
    profile_retrieval = RetrievalService(index=FakeIndex(catalog)).retrieve_profile(
        resolution, gating=gating
    )

    for zone in resolution.zones:
        retrieved = profile_retrieval.zone(zone.zone.zone_id)
        for capability in zone.capabilities:
            hit = retrieved.capability(capability.capability.id)
            if not capability.options or not hit.widening:
                continue
            facts = facts_for(capability, hit, zone.zone)
            reply = batch_json(
                [
                    entry(candidate.control_id, DESCRIPTIVE, [candidate.allowed[0].value])
                    for candidate in facts.candidates
                ]
            )
            return zone.zone.zone_id, capability.capability.id, hit.offered_control_ids, reply

    raise AssertionError("profile A should offer a capability with catalog and RAG candidates")


# --- POST /baseline/compose ---------------------------------------------------


@pytest.fixture
def engine_run(client: TestClient, offline_candidates: CandidatesService) -> dict[str, Any]:
    """A recorded core run for PROFILE-A: what a composition is signed on top of.

    Produced through the real endpoint, not by seeding the ledger, so the test
    exercises that `POST /candidates` records a run whose id
    `POST /baseline/compose` then admits.
    """
    response = client.post(f"{PREFIX}/candidates", json={"profile_id": "PROFILE-A"})
    assert response.status_code == 200, response.text
    return dict(response.json())


@pytest.fixture
def explainable(
    catalog: Catalog,
    resolution_a: ProfileResolution,
    gating_a: ProfileGating,
    overrides: ExitStack,
) -> dict[str, Any]:
    """A capability of profile A whose candidates the scripted model explains in full."""
    zone_id, capability_id, offered, reply = _first_explainable(catalog, resolution_a, gating_a)

    agent = explain_agent()
    overrides.enter_context(agent.override(model=scripted_model(reply)))
    _install_candidates(
        CandidatesService(
            retrieval=RetrievalService(index=FakeIndex(catalog)),
            explainer=CandidateExplanationService(agent=agent),
        )
    )
    return {"zone_id": zone_id, "capability_id": capability_id, "offered": offered}
