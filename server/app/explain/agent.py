"""The Pydantic AI agent that writes the candidate explanations, against Ollama.

Same model, provider and decoding parameters as the parse — the reasoning is
written out in `app/parse/agent.py` and not repeated here. Two differences worth
naming:

**Retries are one, not three.** A malformed explanation costs a paragraph, and
the deterministic rationale is already on screen underneath it. P1 must never
spend the operator's time.

**The output type is a batch.** One request explains every candidate of a
capability, which bounds the model calls to the capabilities the operator opens
and gives the model the whole screen at once. It costs real time — ~12 candidates
is ~900 tokens, and the 7B decodes at ~3.5 tok/s on the reference CPU machine —
which is what `EXPLAIN_TIMEOUT_SECONDS` is for.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_ai import Agent, NativeOutput
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIChatModelSettings
from pydantic_ai.providers.ollama import OllamaProvider

from app.core.config import settings
from app.explain.prompt import SYSTEM_PROMPT
from app.explain.schemas import ExplanationBatch

ExplainAgent = Agent[None, ExplanationBatch]

# A validation failure here is a paragraph, not a profile: one retry, then the
# engine's own rationale stands in.
EXPLAIN_RETRIES = 1


def model_settings() -> OpenAIChatModelSettings:
    """The decoding parameters the request can carry, all from `Settings`."""
    return OpenAIChatModelSettings(
        temperature=settings.LLM_TEMPERATURE,
        top_p=settings.LLM_TOP_P,
        seed=settings.LLM_SEED,
        max_tokens=settings.LLM_NUM_PREDICT,
        timeout=float(settings.EXPLAIN_TIMEOUT_SECONDS),
    )


@lru_cache(maxsize=1)
def explain_agent() -> ExplainAgent:
    """The explanation agent, built once per process."""
    provider = OllamaProvider(base_url=f"{settings.OLLAMA_BASE_URL.rstrip('/')}/v1")
    model = OpenAIChatModel(settings.LLM_MODEL, provider=provider)

    return Agent(
        model,
        output_type=NativeOutput(ExplanationBatch),
        system_prompt=SYSTEM_PROMPT,
        model_settings=model_settings(),
        retries=EXPLAIN_RETRIES,
        name="candidate-explain",
    )
