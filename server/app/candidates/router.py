"""`POST /candidates`: profile in, side-by-side options per capability out.

Every equivalent option for a capability in a zone (framework, jurisdiction,
strength, mapping type, coverage weight, tier) side by side, with the engine's
reason for each and no recommendation — the choice and signature are the human's.
The route resolves the profile and hands off to the service, which writes the run
to the append-only log; the response `run_id` is what `POST /baseline/compose`
quotes so the human's decisions chain onto the run they were made from.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import AuditDep, CandidatesDep, requested_profile
from app.candidates.schemas import CandidatesRequest, CandidatesResponse
from app.core.schemas import Message

router = APIRouter(tags=["candidates"])


@router.post(
    "/candidates",
    response_model=CandidatesResponse,
    status_code=status.HTTP_200_OK,
    summary="Perfil → opciones equivalentes por capacidad y zona",
    responses={
        422: {
            "model": Message,
            "description": "Perfil ausente o ambiguo, o alcance de explicación desconocido.",
        }
    },
)
async def candidates(
    request: CandidatesRequest, service: CandidatesDep, audit: AuditDep
) -> CandidatesResponse:
    """Run the core, widen with retrieval, record the run, and offer every option."""
    profile = requested_profile(request.profile, request.profile_id)
    return await service.candidates_for(profile, request, audit)
