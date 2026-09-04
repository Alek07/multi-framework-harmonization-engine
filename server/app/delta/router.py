"""`POST /delta`: the regional delta for one zone of one asset.

The body names the asset the way `POST /candidates` and `POST /baseline/compose`
do — `profile` inline or `profile_id`, never both. `POST /delta` replaced an
earlier `GET /delta` that could only be asked about profiles frozen in the repo,
which is exactly the question the engine is not for; the replacement did not grow
the closed surface (invariant 4).

`regions` is read both ways — `["US,EU"]` and `["US","EU"]`. Order is meaningful
and not sorted away: the readings are cumulative, so `EU,US` asks a different
question. An unknown region, a single region, a repeated one, an unknown profile
or a zone the profile does not declare are all 422 before any work is done.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import DeltaDep, requested_profile
from app.catalog.schemas import Jurisdiction
from app.core.exceptions import AppException
from app.core.schemas import Message
from app.delta.schemas import DeltaRequest, RegionalDelta

router = APIRouter(tags=["delta"])


class RegionsQueryError(AppException):
    """The `regions` query does not describe a comparison the engine can make."""

    status_code = 422


def parse_regions(raw: list[str]) -> list[Jurisdiction]:
    """`['US,EU']` or `['US', 'EU']` -> `[US, EU]`, in the order asked for.

    Duplicates are rejected rather than silently collapsed: `?regions=US,US` is a
    request nobody meant to write, and answering it with a one-region "delta"
    would be answering a different question than the one asked.
    """
    names = [part.strip().upper() for value in raw for part in value.split(",") if part.strip()]

    regions: list[Jurisdiction] = []
    for name in names:
        try:
            region = Jurisdiction(name)
        except ValueError as exc:
            valid = [j.value for j in Jurisdiction]
            raise RegionsQueryError(
                f"'{name}' no es una jurisdicción del catálogo. Válidas: {valid}."
            ) from exc
        if region in regions:
            raise RegionsQueryError(f"La jurisdicción '{region.value}' aparece repetida.")
        regions.append(region)

    if len(regions) < 2:
        raise RegionsQueryError(
            "Un delta regional compara al menos dos jurisdicciones: indique, por ejemplo, "
            "'regions=US,EU'."
        )
    return regions


@router.post(
    "/delta",
    response_model=RegionalDelta,
    status_code=status.HTTP_200_OK,
    summary="Delta regional (p. ej. US vs. +EU) para una zona del activo",
    responses={422: {"model": Message, "description": "Regiones, perfil o zona inválidos."}},
)
async def regional_delta(request: DeltaRequest, service: DeltaDep) -> RegionalDelta:
    """Read one zone under each region and report what changes between the readings.

    `mode` (cumulative or symmetric) and `regime` (all jurisdictions or
    law-against-law) are the human's choice, validated as typed enums by the
    request model. The zone is checked by the service, so the route only turns the
    request into the engine's types. A delta writes nothing — it decides nothing,
    changes no baseline and belongs to no run — so there is no audit dependency and
    the call is safe to repeat.
    """
    return service.delta(
        requested_profile(request.profile, request.profile_id),
        request.zone_id,
        parse_regions(request.regions),
        request.mode,
        request.regime,
    )
