"""UCM-15 - `POST /asset/parse`: free text in, a reviewable draft out.

The endpoint is thin because the service is (`parse/service.py`), and both are
thin for the same reason: the LLM extracts, it does not decide (invariant 1).
What the route is careful *not* to do is worth stating.

* **It does not write to the audit log.** A draft is a proposal, and a proposal
  enters the ledger when the operator confirms it — as a human decision, with the
  human's justification (UCM-11).
* **It does not return an `AssetProfile`.** It returns a `ParseResult`:
  the draft, the paths still missing, and the provenance of the run.
  `review_required` is a constant `True`.
* **There is no endpoint to promote a draft into a profile,** and that is not an
  omission. The operator corrects the draft, and the corrected `AssetProfile` is
  what the next call (`POST /candidates`) carries. Adding a sixth endpoint to
  perform `completion.to_profile` — a pure, offline function — would open a closed
  surface (invariant 4) to buy nothing.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import ParseDep
from app.core.schemas import Message
from app.parse.schemas import AssetParseRequest, ParseResult

router = APIRouter(tags=["asset"])


@router.post(
    "/asset/parse",
    response_model=ParseResult,
    status_code=status.HTTP_200_OK,
    summary="Texto libre → borrador de AssetProfile (revisable)",
    responses={
        422: {"model": Message, "description": "La descripción está vacía."},
        502: {"model": Message, "description": "El modelo no devolvió un borrador válido."},
        503: {"model": Message, "description": "Ollama no está disponible o sirve otro modelo."},
    },
)
async def parse_asset(request: AssetParseRequest, service: ParseDep) -> ParseResult:
    """Parse an asset description into a draft the operator reviews and corrects."""
    return await service.parse(request.description, request.profile_id)
