"""UCM-15 - `POST /candidates`: profile in, side-by-side options per capability out.

This is the endpoint the central contribution runs on. A crosswalk *translates*
(A ≈ B); what this returns is every equivalent option for a capability in a zone —
framework, jurisdiction, strength, mapping type, coverage weight, tier — next to
each other, with the engine's reason for each one and no recommendation attached.
The choice, and the signature, are the human's (UCM-16).

The route itself does almost nothing: it resolves which profile the request is
about and hands the work to the service, which is also what writes the run to the
append-only log. The `run_id` in the response is what `POST /baseline/compose`
quotes, so the human's decisions chain onto the engine run they were made from.
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
