"""UCM-12 - The parse use case: description in, reviewable draft out.

The service is deliberately thin, and what it refuses to do matters more than
what it does.

* **It does not write to the audit log.** The LLM is not an actor (UCM-11): it
  neither decides nor ranks nor filters. What it produces is a proposal, and the
  proposal enters the log when the operator confirms it — as a *human* decision,
  with the human's justification. Logging the parse as an engine event would put
  a model's guess on the record as an engine decision.
* **It does not complete the draft.** Missing values are reported
  (`missing_required`), never defaulted. The path from draft to `AssetProfile`
  runs through `completion.to_profile`, after review.
* **It does not run without a verified model.** `verify_model` is awaited before
  the first token: a draft produced by unpinned weights is not reproducible, and
  the draft itself carries no sign of it.

Everything the parse depended on ends up in `ParseProvenance`, including the
number of model requests it took, so an evaluation run (UCM-18) can report how
often the retry loop was needed instead of guessing.
"""

from __future__ import annotations

import hashlib

from pydantic_ai import UnexpectedModelBehavior
from pydantic_ai.messages import ModelResponse

from app.core.config import settings
from app.core.exceptions import AppException
from app.parse.agent import ParseAgent, parse_agent
from app.parse.completion import missing_required, profile_id_for
from app.parse.ollama import verify_model
from app.parse.prompt import PROMPT_VERSION, user_prompt
from app.parse.schemas import ParseProvenance, ParseResult


class EmptyDescriptionError(AppException):
    """Nothing to parse. Not a model failure, so it never reaches the model."""

    status_code = 422


class ParseFailedError(AppException):
    """The model could not produce a valid draft within the allowed retries."""

    status_code = 502


class AssetParseService:
    """Free text -> `ParseResult`. The agent is injectable so tests never need Ollama."""

    def __init__(self, agent: ParseAgent | None = None):
        self.agent = agent if agent is not None else parse_agent()

    async def parse(self, description: str, profile_id: str | None = None) -> ParseResult:
        """Parse an operator's description into a draft awaiting review."""
        if not description or not description.strip():
            raise EmptyDescriptionError("La descripción del activo está vacía.")

        digest = await verify_model()

        try:
            run = await self.agent.run(user_prompt(description))
        except UnexpectedModelBehavior as exc:
            raise ParseFailedError(
                f"El modelo no devolvió un perfil válido tras {settings.LLM_MAX_RETRIES} "
                f"reintentos: {exc}"
            ) from exc

        draft = run.output
        attempts = sum(1 for message in run.all_messages() if isinstance(message, ModelResponse))

        return ParseResult(
            profile_id=profile_id_for(draft, profile_id),
            draft=draft,
            missing_required=missing_required(draft),
            provenance=ParseProvenance(
                model=settings.LLM_MODEL,
                model_digest=digest,
                prompt_version=PROMPT_VERSION,
                temperature=settings.LLM_TEMPERATURE,
                seed=settings.LLM_SEED,
                top_p=settings.LLM_TOP_P,
                num_predict=settings.LLM_NUM_PREDICT,
                attempts=attempts,
                source_sha256=hashlib.sha256(description.strip().encode("utf-8")).hexdigest(),
            ),
        )
