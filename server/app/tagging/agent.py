"""The Pydantic AI agent that proposes a control's premises.

Same shape as the parse and explain agents: `NativeOutput` so llama.cpp
grammar-constrains decoding, temperature 0 with a fixed seed for reproducibility
(invariant 3), and a retry budget spent by appending the validation error to the
history rather than rerolling.

The one deliberate difference is that it reuses `LLM_TIMEOUT_SECONDS` rather than a
budget of its own: the answer for one control is a handful of short fields, and
this runs offline from a script where a slow control costs a reviewer nothing.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_ai import Agent, NativeOutput
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIChatModelSettings
from pydantic_ai.providers.ollama import OllamaProvider

from app.core.config import settings
from app.tagging.prompt import SYSTEM_PROMPT
from app.tagging.schemas import ControlTagDraft

TaggingAgent = Agent[None, ControlTagDraft]


def model_settings() -> OpenAIChatModelSettings:
    """The decoding parameters the request can carry, all from `Settings`."""
    return OpenAIChatModelSettings(
        temperature=settings.LLM_TEMPERATURE,
        top_p=settings.LLM_TOP_P,
        seed=settings.LLM_SEED,
        max_tokens=settings.LLM_NUM_PREDICT,
        timeout=float(settings.LLM_TIMEOUT_SECONDS),
    )


@lru_cache(maxsize=1)
def tagging_agent() -> TaggingAgent:
    """The tagging agent, built once per process."""
    provider = OllamaProvider(base_url=f"{settings.OLLAMA_BASE_URL.rstrip('/')}/v1")
    model = OpenAIChatModel(settings.LLM_MODEL, provider=provider)

    return Agent(
        model,
        output_type=NativeOutput(ControlTagDraft),
        system_prompt=SYSTEM_PROMPT,
        model_settings=model_settings(),
        retries=settings.LLM_MAX_RETRIES,
        name="control-tagging",
    )
