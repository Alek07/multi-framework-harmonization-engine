"""What Ollama is actually serving, checked before it is trusted.

An Ollama tag is mutable, so reproducibility (invariant 3) rests on the manifest
digest, not the tag: the engine asks `/api/tags` which digest is behind the name
and refuses to parse against anything else. The check is lazy and cached, not done
at startup, so the API can come up while Ollama is still pulling (the compose
healthcheck can take ~20 min on the first run) without the backend crash-looping.
`verify_model` guarantees no draft is ever produced by an unverified model — it is
the first thing every parse awaits.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings
from app.core.exceptions import AppException


class ModelUnavailableError(AppException):
    """Ollama is unreachable, or the pinned model is not on disk yet."""

    status_code = 503


class ModelMismatchError(AppException):
    """Ollama serves this tag, but not the weights the POC was evaluated with."""

    status_code = 503


# Digest of the verified model, kept for the process' lifetime. A pull that
# replaces the weights under a running backend is a restart, not a hot swap.
_verified_digest: str | None = None


def _normalise(digest: str) -> str:
    """Ollama reports digests as `sha256:<hex>` in some versions and bare in others."""
    return digest.split(":", 1)[-1].strip().lower()


async def _tags() -> list[dict[str, Any]]:
    url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/tags"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ModelUnavailableError(f"No se pudo consultar Ollama en {url}: {exc}") from exc

    models = response.json().get("models", [])
    return models if isinstance(models, list) else []


async def verify_model() -> str:
    """Return the digest Ollama serves for the pinned tag, or refuse to go on.

    Raising is the point: a parse against the wrong weights would still produce a
    well-formed draft that neither the operator nor the audit log could catch.
    """
    global _verified_digest
    if _verified_digest is not None:
        return _verified_digest

    available = await _tags()
    served = next(
        (m.get("digest", "") for m in available if m.get("name") == settings.LLM_MODEL), None
    )
    if served is None:
        names = ", ".join(sorted(str(m.get("name", "")) for m in available)) or "ninguno"
        raise ModelUnavailableError(
            f"Ollama no tiene el modelo '{settings.LLM_MODEL}' (disponibles: {names})"
        )

    expected = _normalise(settings.LLM_MODEL_DIGEST)
    if _normalise(served) != expected:
        raise ModelMismatchError(
            f"El modelo '{settings.LLM_MODEL}' que sirve Ollama tiene el digest "
            f"{_normalise(served)}, no el fijado {expected}. La etiqueta ha cambiado: no se "
            "puede garantizar que dos ejecuciones den el mismo resultado con estos pesos."
        )

    _verified_digest = _normalise(served)
    return _verified_digest


async def warm_model() -> None:
    """Load the verified weights into memory, so the first parse does not pay for it.

    An empty prompt is Ollama's documented preload: no token is decoded, so no output
    can depend on it. `keep_alive` is sent on the native API because the
    OpenAI-compatible surface drops it, like `num_ctx` (see `agent.py`).
    """
    await verify_model()  # cached, so the first parse skips the digest check too

    url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/generate"
    payload = {"model": settings.LLM_MODEL, "prompt": "", "keep_alive": settings.LLM_KEEP_ALIVE}
    try:
        async with httpx.AsyncClient(timeout=float(settings.LLM_TIMEOUT_SECONDS)) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ModelUnavailableError(f"No se pudo precargar el modelo en {url}: {exc}") from exc


def reset_verification() -> None:
    """Forget the cached digest. For tests, and for a deliberate model change."""
    global _verified_digest
    _verified_digest = None
