"""UCM-15 - Fixtures for the closed surface: the shipped app, and no network at all.

Same rule the rest of the suite follows (UCM-12/13/14): these tests run on any
machine, offline, with no Ollama, no Qdrant and no embedding model on disk. What
is replaced is exactly three things — the LLM's replies, the vectors, and the
digest check — and they are replaced by the *same* stand-ins the unit suites
already use, so what is exercised end to end here is the shipped code path: the
real routers, the real dependency wiring, the real deterministic core, the real
audit ledger and the real Pydantic contracts.

The overrides go through `app.dependency_overrides`, which is why `app/api/deps.py`
exposes the services as dependencies rather than importing them inside the
handlers: a route that reached for a singleton directly could not be tested
without a container. The agents are process-wide (`lru_cache`), so every override
of one is entered on an `ExitStack` that the fixture unwinds — a scripted model
left installed would silently script the next test too.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import ExitStack
from typing import Any

import pydantic_ai.models
import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.api.deps import candidates_service, parse_service
from app.candidates.service import CandidatesService
from app.catalog.schemas import Catalog
from app.core.config import settings
from app.engine.schemas import ProfileResolution
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
    catalog: Catalog, resolution: ProfileResolution
) -> tuple[str, str, list[str], str]:
    """A capability with both kinds of candidate, and the reply that explains them.

    The reply is built from the *actual* candidates the service will offer — the
    core's resolution plus the RAG pass over it — because `CapabilityExplanations`
    refuses to be built unless the explanations are exactly the offered candidates,
    in order. Scripting anything else would test the validator, not the wiring.
    """
    profile_retrieval = RetrievalService(index=FakeIndex(catalog)).retrieve_profile(resolution)

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


@pytest.fixture
def explainable(
    catalog: Catalog, resolution_a: ProfileResolution, overrides: ExitStack
) -> dict[str, Any]:
    """A capability of profile A whose candidates the scripted model explains in full."""
    zone_id, capability_id, offered, reply = _first_explainable(catalog, resolution_a)

    agent = explain_agent()
    overrides.enter_context(agent.override(model=scripted_model(reply)))
    _install_candidates(
        CandidatesService(
            retrieval=RetrievalService(index=FakeIndex(catalog)),
            explainer=CandidateExplanationService(agent=agent),
        )
    )
    return {"zone_id": zone_id, "capability_id": capability_id, "offered": offered}
