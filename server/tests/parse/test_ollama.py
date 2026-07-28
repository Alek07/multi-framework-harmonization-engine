"""UCM-12 - The digest guard: what Ollama serves is what was evaluated, or nothing.

The tag `qwen2.5:7b-instruct-q4_K_M` is mutable. A run against different weights
under the same name produces a perfectly well-formed draft, so the only place
this can be caught is before the request — which is what these tests hold in
place. `/api/tags` is stubbed; no test here opens a socket.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.core.config import settings
from app.parse import ollama as ollama_module
from app.parse.ollama import (
    ModelMismatchError,
    ModelUnavailableError,
    reset_verification,
    verify_model,
)
from app.parse.service import AssetParseService
from tests.parse.conftest import VERIFIED_DIGEST, draft_json, scripted_agent


@pytest.fixture(autouse=True)
def _forget_verification() -> None:
    reset_verification()


def stub_tags(monkeypatch: pytest.MonkeyPatch, models: list[dict[str, Any]]) -> list[int]:
    """Replace the `/api/tags` call and count how often it is made."""
    calls: list[int] = []

    async def _tags() -> list[dict[str, Any]]:
        calls.append(1)
        return models

    monkeypatch.setattr(ollama_module, "_tags", _tags)
    return calls


async def test_the_pinned_digest_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_tags(monkeypatch, [{"name": settings.LLM_MODEL, "digest": VERIFIED_DIGEST}])

    assert await verify_model() == VERIFIED_DIGEST


async def test_a_prefixed_digest_is_the_same_digest(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ollama writes `sha256:...` in some versions and the bare hex in others."""
    stub_tags(monkeypatch, [{"name": settings.LLM_MODEL, "digest": f"sha256:{VERIFIED_DIGEST}"}])

    assert await verify_model() == VERIFIED_DIGEST


async def test_other_weights_under_the_same_tag_are_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_tags(monkeypatch, [{"name": settings.LLM_MODEL, "digest": "0" * 64}])

    with pytest.raises(ModelMismatchError):
        await verify_model()


async def test_a_missing_model_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_tags(monkeypatch, [{"name": "llama3:8b", "digest": VERIFIED_DIGEST}])

    with pytest.raises(ModelUnavailableError) as excinfo:
        await verify_model()

    assert "llama3:8b" in excinfo.value.detail


async def test_the_digest_is_checked_once_per_process(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = stub_tags(monkeypatch, [{"name": settings.LLM_MODEL, "digest": VERIFIED_DIGEST}])

    await verify_model()
    await verify_model()

    assert len(calls) == 1


async def test_no_draft_exists_without_a_verified_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """The guard is a precondition of the parse, not an advisory check.

    The autouse stub of `conftest` is undone here on purpose: this is the one
    test that exercises the service against an unverified Ollama.
    """
    monkeypatch.setattr(ollama_module, "_verified_digest", None)
    monkeypatch.setattr("app.parse.service.verify_model", verify_model)
    stub_tags(monkeypatch, [{"name": settings.LLM_MODEL, "digest": "0" * 64}])

    with scripted_agent(draft_json()) as agent:
        with pytest.raises(ModelMismatchError):
            await AssetParseService(agent).parse("Una estación de ingeniería.")
