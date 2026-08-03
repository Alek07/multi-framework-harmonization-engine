"""UCM-14 - The Pydantic AI agent that writes the explanations, against Ollama.

Same model, same provider and same decoding parameters as the parse (UCM-12),
because it is the same pinned weights doing both jobs and reproducibility is
declared once, not per feature: `temperature`, `top_p`, `seed` and `num_predict`
travel in the request from `Settings`; `num_ctx` is applied server-side through
`OLLAMA_CONTEXT_LENGTH`; `top_k` and `repeat_penalty` are the Ollama server's
defaults, pinned by the compose file's image digest. The reasoning behind each of
those is written out in `app/parse/agent.py` and not repeated here.

Two differences worth naming.

**Retries are one, not three.** A malformed parse costs the operator the whole
profile, so it is worth three attempts. A malformed explanation costs a
paragraph, and the deterministic rationale is already on screen underneath it —
so this agent tries once more and then gets out of the way. P1 must never spend
the operator's time.

**The output type is a batch.** One request explains every candidate of a
capability, which bounds the number of model calls to the number of capabilities
the operator actually opens, and gives the model the whole screen at once —
without that context it would describe candidate 4 as if candidates 1-3 did not
exist. It also costs real time: ~12 candidates is ~900 generated tokens, and the
7B decodes at ~3.5 tok/s on the reference CPU machine, so the request needs
minutes rather than seconds. That is what `EXPLAIN_TIMEOUT_SECONDS` is for, and
why the explanations are computed for the capability the operator opened rather
than for a whole profile.
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
