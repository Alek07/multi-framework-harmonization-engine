"""UCM-12 - The Pydantic AI agent that runs the parse against Ollama.

Two decisions here are load-bearing.

**Native structured output, not tool calling.** Ollama's OpenAI-compatible
endpoint accepts a JSON schema as `response_format`, and llama.cpp then
constrains decoding to that grammar. A 7B model asked to *call a tool* with this
schema improvises far more often than one that is grammatically unable to emit an
invalid shape. `NativeOutput` is what selects that path; the retries below then
only have to cover semantic failures, not syntax.

**Where each decoding parameter is pinned.** Reproducibility (invariant 3) needs
every sampling knob fixed, but they are not all fixed in the same place, and
pretending otherwise would be the kind of unchecked claim this project exists to
avoid:

* `temperature`, `top_p`, `seed` and `num_predict` travel in the request, from
  `Settings` — temperature 0 makes decoding greedy and the seed fixes what little
  is left.
* `num_ctx` cannot travel in the request: Ollama's OpenAI-compatible endpoint
  maps a fixed set of OpenAI fields and drops anything else, an `options` object
  included (checked against the running service, not assumed). It is set
  server-side instead, through `OLLAMA_CONTEXT_LENGTH` in the compose file, from
  the same `LLM_NUM_CTX` value — a context window quietly smaller than the prompt
  truncates the instructions rather than failing, which is the worst failure mode
  available here.
* `top_k` and `repeat_penalty` are unreachable for the same reason, and
  `qwen2.5:7b-instruct-q4_K_M` ships no `PARAMETER` line of its own, so they are
  the Ollama server's defaults. What pins them is the compose file's **image**
  digest rather than the model digest. That is a weaker guarantee than the rest
  and is written down here as such; greedy decoding makes `top_k` inert anyway,
  and the repeat penalty is then a constant of the pinned image.
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

    `retries` is not a reroll of the same prompt: on a validation failure Pydantic
    AI appends the error to the message history, so the next request is a
    genuinely different — and still deterministic — conversation. That is what
    makes 'retry on format failure' compatible with a fixed seed.
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
