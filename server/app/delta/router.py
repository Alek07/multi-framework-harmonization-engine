"""UCM-15/UCM-17 - `GET /delta?regions=US,EU`: the regional delta for the demo zone.

UCM-15 fixed the contract; UCM-17 fills it in. The route validates the query and
hands over: an unknown region, a single region, a repeated one, an unknown profile
or a zone the profile does not declare are all 422 before any work is done.

`regions` is read both ways — `?regions=US,EU` and `?regions=US&regions=EU` — for
one reason: the first is the form written into the PRD and the ticket, and an API
that documents a URL it cannot parse is worse than one that accepts two spellings.

The order of the regions is meaningful and is not sorted away. The readings are
cumulative — `US,EU` means "the US reading, then the same plus the European
obligation overlay" — so `EU,US` asks a different, equally legitimate question.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DeltaDep, requested_profile
from app.catalog.schemas import Jurisdiction
from app.core.exceptions import AppException
from app.core.schemas import Message
from app.delta.schemas import RegionalDelta

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


@router.get(
    "/delta",
    response_model=RegionalDelta,
    status_code=status.HTTP_200_OK,
    summary="Delta regional (p. ej. US vs. +EU) para una zona del perfil",
    responses={422: {"model": Message, "description": "Regiones, perfil o zona inválidos."}},
)
async def regional_delta(
    service: DeltaDep,
    regions: Annotated[
        list[str],
        Query(
            description=(
                "Jurisdicciones a comparar en orden, p. ej. 'US,EU'. Mínimo dos, sin repetir. "
                "Las lecturas son acumulativas: la segunda es la primera más esa región."
            )
        ),
    ],
    profile_id: Annotated[
        str, Query(description="Perfil congelado en el repositorio, p. ej. 'PROFILE-A'.")
    ],
    zone_id: Annotated[
        str,
        Query(
            description=(
                "Zona del perfil sobre la que se calcula el delta. Una sola: N zonas por "
                "consulta son trabajo futuro declarado."
            )
        ),
    ],
) -> RegionalDelta:
    """Read one zone under each region's cumulative lens and report what changes.

    The zone is checked by the service — it is the one that knows what a zone has
    to be to be read — so the route only turns the query into the engine's own
    types and gets out of the way.
    """
    return service.delta(
        requested_profile(None, profile_id), zone_id, parse_regions(regions)
    )
