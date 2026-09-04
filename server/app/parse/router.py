"""`POST /asset/parse`: free text in, a reviewable draft out.

Thin because the LLM extracts, it does not decide (invariant 1). The route does not
write to the audit log (a draft is a proposal; it enters the ledger only when the
operator confirms it, as a human decision) and does not return an `AssetProfile` but
a `ParseResult` (draft, missing paths, provenance; `review_required` is constant
`True`). There is deliberately no endpoint to promote a draft into a profile: the
operator corrects the draft and the corrected `AssetProfile` is what `POST /candidates`
carries — adding one for the offline `completion.to_profile` would open a closed
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
        503: {
            "model": Message,
            "description": (
                "Ollama no está disponible, sirve otro modelo, o no respondió a tiempo."
            ),
        },
    },
)
async def parse_asset(request: AssetParseRequest, service: ParseDep) -> ParseResult:
    """Parse an asset description into a draft the operator reviews and corrects."""
    return await service.parse(request.description, request.profile_id)
