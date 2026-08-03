"""UCM-15 - `GET /delta?regions=US,EU`: the regional delta for the demo zone.

The logic is UCM-17's. What this ticket fixes is the contract, and the route
validates it for real: an unknown region, a single region, an unknown profile or a
zone the profile does not declare are all 422 today. A well-formed request reaches
501, which says the endpoint exists and the logic is the next ticket.

`regions` is read both ways — `?regions=US,EU` and `?regions=US&regions=EU` — for
one reason: the first is the form written into the PRD and the ticket, and an API
that documents a URL it cannot parse is worse than one that accepts two spellings.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import requested_profile
from app.catalog.schemas import Jurisdiction
from app.core.exceptions import AppException, NotImplementedYetError
from app.core.schemas import Message
from app.delta.schemas import RegionalDelta

router = APIRouter(tags=["delta"])

DELTA_PENDING = (
    "El delta regional se implementa en UCM-17. El contrato de esta consulta es firme y ya se "
    "valida: lo que falta es la lógica, no el endpoint. La superficie de la API sigue cerrada "
    "en cinco endpoints."
)


class RegionsQueryError(AppException):
    """The `regions` query does not describe a comparison the engine can make."""

    status_code = 422


class UnknownZoneError(AppException):
    """The profile does not declare the zone the delta was asked about."""

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
    responses={
        422: {"model": Message, "description": "Regiones, perfil o zona inválidos."},
        501: {"model": Message, "description": "Pendiente de UCM-17 (contrato ya validado)."},
    },
)
async def regional_delta(
    regions: Annotated[
        list[str],
        Query(description="Jurisdicciones a comparar, p. ej. 'US,EU'. Mínimo dos, sin repetir."),
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
    """Read one zone under each jurisdiction's lens and report what changes (UCM-17)."""
    parse_regions(regions)
    profile = requested_profile(None, profile_id)

    declared = [zone.id for zone in profile.zones]
    if zone_id not in declared:
        raise UnknownZoneError(
            f"El perfil '{profile.id}' no declara la zona '{zone_id}'. Zonas: {declared}."
        )

    raise NotImplementedYetError(DELTA_PENDING)
