"""The Pydantic AI agent that runs the parse against Ollama.

Uses native structured output (JSON-schema-constrained decoding via `NativeOutput`),
not tool calling: a 7B model grammatically unable to emit an invalid shape
improvises far less. Reproducibility (invariant 3) needs every sampling knob fixed,
but not all in the same place: `temperature`, `top_p`, `seed` and `num_predict`
travel in the request from `Settings` (temp 0 makes decoding greedy); `num_ctx` is
set server-side via `OLLAMA_CONTEXT_LENGTH` because Ollama's OpenAI-compatible
endpoint drops any `options` object; `top_k` and `repeat_penalty` are the server's
defaults, pinned only by the compose image digest (a weaker guarantee, and greedy
decoding makes `top_k` inert anyway).
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_ai import Agent, NativeOutput
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIChatModelSettings
from pydantic_ai.providers.ollama import OllamaProvider

from app.core.config import settings
from app.parse.prompt import SYSTEM_PROMPT
from app.parse.schemas import AssetProfileDraft

ParseAgent = Agent[None, AssetProfileDraft]


def model_settings() -> OpenAIChatModelSettings:
    """The decoding parameters that the request can carry, all from `Settings`."""
    return OpenAIChatModelSettings(
        temperature=settings.LLM_TEMPERATURE,
        top_p=settings.LLM_TOP_P,
        seed=settings.LLM_SEED,
        max_tokens=settings.LLM_NUM_PREDICT,
        timeout=float(settings.LLM_TIMEOUT_SECONDS),
    )


@lru_cache(maxsize=1)
def parse_agent() -> ParseAgent:
    """The parse agent, built once per process.

    `retries` is not a reroll: on a validation failure Pydantic AI appends the error
    to the message history, so the next request is a different — and still
    deterministic — conversation, which is what makes retry compatible with a fixed seed.
    """
    provider = OllamaProvider(base_url=f"{settings.OLLAMA_BASE_URL.rstrip('/')}/v1")
    model = OpenAIChatModel(settings.LLM_MODEL, provider=provider)

    return Agent(
        model,
        output_type=NativeOutput(AssetProfileDraft),
        system_prompt=SYSTEM_PROMPT,
        model_settings=model_settings(),
        retries=settings.LLM_MAX_RETRIES,
        name="asset-parse",
    )
