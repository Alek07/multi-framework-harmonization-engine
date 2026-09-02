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
import logging

from pydantic_ai import UnexpectedModelBehavior
from pydantic_ai.exceptions import ModelAPIError
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


class ParseUnavailableError(AppException):
    """The model was asked and did not answer: a timeout, or the provider refusing.

    Distinct from `ParseFailedError` on purpose, and the distinction is the
    operator's, not ours: a model that answered badly is a reason to review the
    draft, and a model that did not answer at all is a reason to try again. They
    also have different fixes, so they get different status codes.
    """

    status_code = 503


logger = logging.getLogger(__name__)

# Reached most often on the first parse after a cold start: the weights are on
# disk, not in memory, and loading ~4.7 GB takes longer than the request budget
# (measured: 77 s warm, 262 s cold, against `LLM_TIMEOUT_SECONDS` of 180). Before
# v0.5.0 that surfaced as an unhandled 500 with a Python traceback -- the one path
# in this project where the operator got a stack trace instead of a sentence.
UNAVAILABLE_NOTICE = (
    "El modelo no respondió a tiempo. El primer análisis después de arrancar el sistema "
    "carga el modelo en memoria y tarda bastante más que los siguientes, así que volver a "
    "intentarlo suele bastar. Si se repite, comprueba que Ollama sigue en pie."
)


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
        except ModelAPIError as exc:
            # A timeout, a refused connection, a provider error: the model never
            # answered, so there is nothing to review and nothing to report about
            # it beyond that it did not answer.
            logger.warning("parse: the model did not answer (%s)", exc)
            raise ParseUnavailableError(UNAVAILABLE_NOTICE) from exc
        except Exception as exc:  # noqa: BLE001 - the operator never reads a traceback
            # The house rule, applied here too: whatever went wrong, what reaches
            # the screen is a sentence written for the person in front of it. The
            # Python message goes to the log, where a developer will look for it.
            logger.exception("parse failed on a %d-character description", len(description))
            raise ParseUnavailableError(UNAVAILABLE_NOTICE) from exc

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
