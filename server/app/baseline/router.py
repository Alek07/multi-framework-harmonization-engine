"""UCM-15/UCM-16 - `POST /baseline/compose`, `GET /baseline/{id}/audit-log`, `GET /baselines`.

The first two are halves of the same promise. One is where the human composes and
signs; the other is where anyone can check what was signed and why. UCM-15 declared
both contracts; UCM-16 fills the composition in without changing what a client
sends.

The third answers the question neither of them can: *what has been signed here?*
Both of the others take a baseline id, which assumes the caller already has one —
true for the client that just signed, false for anyone who opens the application
afterwards. It is a read over the ledger and adds no state of its own
(`baseline/listing.py`).

One note on the trail. It is served by baseline id, and it deliberately returns
*more* than the events stamped with that baseline: the engine's decisions are
recorded before a baseline exists — they are what the human composed from — so the
query walks back to the runs those events belong to (`trail_for_baseline`).
Serving only the signed events would be a trail that starts after the interesting
part.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status

from app.api.deps import AuditDep, CompositionDep, requested_profile
from app.audit.schemas import AuditActor, AuditEventRead
from app.baseline.listing import listing_of
from app.baseline.schemas import (
    BaselineAuditLog,
    BaselineList,
    ComposedBaseline,
    ComposeRequest,
)
from app.core.exceptions import NotFoundError
from app.core.schemas import Message

router = APIRouter(prefix="/baseline", tags=["baseline"])

# The list is about baselines in the plural, so it does not live under the prefix
# of a single one. A second router rather than a bare path on the first, so the
# mounting stays as explicit as the surface it is declared in (`api/router.py`).
collection_router = APIRouter(tags=["baseline"])


@collection_router.get(
    "/baselines",
    response_model=BaselineList,
    status_code=status.HTTP_200_OK,
    summary="Líneas base firmadas en esta bitácora",
)
async def list_baselines(audit: AuditDep) -> BaselineList:
    """Every signed baseline the ledger holds, newest first.

    Nothing is stored to answer this: a signed baseline *is* its `baseline_signed`
    entry, and the summary is that entry read back plus a few tallies counted over
    the entries stamped with the same baseline. An empty ledger is an empty list
    and a 200 — "nothing has been signed here" is an answer, not a missing
    resource.
    """
    return listing_of(await audit.signed_baselines(), await audit.composition_counts())


@router.post(
    "/compose",
    response_model=ComposedBaseline,
    status_code=status.HTTP_201_CREATED,
    summary="Elecciones del humano → línea base firmada",
    responses={
        422: {
            "model": Message,
            "description": "Elecciones, firma o ejecución del motor inválidas.",
        },
        409: {
            "model": Message,
            "description": (
                "No se puede firmar: bloque obligatorio incompleto, ejecución ya firmada o "
                "entradas versionadas cambiadas."
            ),
        },
    },
)
async def compose_baseline(
    request: ComposeRequest, service: CompositionDep, audit: AuditDep
) -> ComposedBaseline:
    """Record every choice, verify Tier 0 is complete, and sign the baseline (UCM-16).

    The route stays thin on purpose: it resolves which profile the composition is
    about and hands over. Everything that decides whether a signature is admissible
    — the run exists, the versions have not moved, no mandate is open, the run has
    not been signed already — lives in the service, next to the reasons for it.
    """
    profile = requested_profile(request.profile, request.profile_id)
    return await service.compose(profile, request, audit)


@router.get(
    "/{baseline_id}/audit-log",
    response_model=BaselineAuditLog,
    status_code=status.HTTP_200_OK,
    summary="Trazabilidad completa de una línea base firmada",
    responses={404: {"model": Message, "description": "No hay bitácora para esa línea base."}},
)
async def baseline_audit_log(baseline_id: UUID, audit: AuditDep) -> BaselineAuditLog:
    """Every event behind one baseline — the engine's run and the human's choices."""
    recorded = await audit.log_for_baseline(baseline_id)
    if not recorded:
        raise NotFoundError(
            f"No hay ningún evento registrado para la línea base '{baseline_id}'. La bitácora "
            "es append-only: si no hay nada, es que esa línea base no se compuso aquí."
        )

    events = [AuditEventRead.model_validate(event) for event in recorded]
    engine_events = sum(1 for event in events if event.actor is AuditActor.ENGINE)
    chain = await audit.verify_baseline(baseline_id)

    return BaselineAuditLog(
        baseline_id=baseline_id,
        events=events,
        chain=chain,
        engine_events=engine_events,
        human_events=len(events) - engine_events,
        rationale=(
            f"Traza completa de la línea base {baseline_id}: {engine_events} decisión(es) del "
            f"motor y {len(events) - engine_events} del humano, en el orden en que se "
            f"registraron. {chain.detail}"
        ),
    )
