"""Everything about a baseline: composing it, its trail, the list, the document.

Compose is where the human composes and signs; audit-log, list and statement are
reads projected from the ledger (they compute and store nothing). The list
answers *what has been signed here?* for a caller with no baseline id; the
statement answers *what applies, what does not, and on whose word?* as a document
(SoA / OSCAL), not a query (`baseline/statement.py`, `baseline/oscal.py`).

The trail is served by baseline id but returns *more* than the events stamped
with it: the engine's decisions are recorded before a baseline exists, so the
query walks back to the runs those events belong to (`trail_for_baseline`).
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status
from fastapi.responses import JSONResponse

from app.api.deps import AuditDep, CompositionDep, requested_profile
from app.audit.schemas import AuditActor, AuditEventRead
from app.baseline.listing import listing_of
from app.baseline.oscal import as_json, oscal_ssp
from app.baseline.schemas import (
    BaselineAuditLog,
    BaselineList,
    BaselineStatement,
    ComposedBaseline,
    ComposeRequest,
    StatementFormat,
)
from app.baseline.statement import StatementNotFoundError, statement_of
from app.core.exceptions import NotFoundError
from app.core.schemas import Message

router = APIRouter(prefix="/baseline", tags=["baseline"])

# `format` on the wire, `document` in the signature: `format` shadows a Python builtin.
FormatQuery = Annotated[
    StatementFormat,
    Query(
        alias="format",
        description=(
            "'soa' (por defecto) devuelve la declaración de aplicabilidad; 'oscal' la misma "
            "declaración como system-security-plan parcial del modelo OSCAL de NIST."
        ),
    ),
]

# Plural, so not under the prefix of a single baseline.
collection_router = APIRouter(tags=["baseline"])


@collection_router.get(
    "/baselines",
    response_model=BaselineList,
    status_code=status.HTTP_200_OK,
    summary="Líneas base firmadas en esta bitácora",
)
async def list_baselines(audit: AuditDep) -> BaselineList:
    """Every signed baseline the ledger holds, newest first.

    An empty ledger is an empty list and a 200: nothing signed is an answer.
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
    """Record every choice, verify Tier 0 is complete, and sign the baseline.

    The route stays thin on purpose: it resolves which profile the composition is
    about and hands over. What decides whether a signature is admissible lives in
    the service, next to the reasons for it.
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
    events = await _trail(baseline_id, audit)
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


@router.get(
    "/{baseline_id}/statement",
    response_model=BaselineStatement,
    status_code=status.HTTP_200_OK,
    summary="Declaración de aplicabilidad de una línea base firmada (SoA · OSCAL)",
    responses={
        404: {"model": Message, "description": "No hay ninguna línea base firmada con ese id."},
    },
)
async def baseline_statement(
    baseline_id: UUID,
    audit: AuditDep,
    document: FormatQuery = StatementFormat.SOA,
) -> BaselineStatement | JSONResponse:
    """The signed baseline as the document a reviewer expects to see.

    One row per required capability per zone, projected from the trail and nothing
    else: it computes nothing, stores nothing, and reports the catalog and rules
    that governed the signature rather than today's.

    `?format=oscal` returns the same content as a partial OSCAL SSP. That branch
    returns a `Response` directly and so bypasses `response_model`, deliberately:
    OSCAL spells its fields with hyphens and omits what it does not know, and
    neither is true of the declaration's own schema.
    """
    events = await _trail(baseline_id, audit)
    chain = await audit.verify_baseline(baseline_id)

    try:
        statement = statement_of(events, baseline_id, chain)
    except StatementNotFoundError as exc:
        raise NotFoundError(
            f"La bitácora tiene entradas de la línea base '{baseline_id}' pero ninguna firma. "
            "Una declaración de aplicabilidad es el documento de una línea base *firmada*: "
            "mientras no haya firma no hay nada que declarar."
        ) from exc

    if document is StatementFormat.OSCAL:
        return JSONResponse(content=as_json(oscal_ssp(statement)))
    return statement


async def _trail(baseline_id: UUID, audit: AuditDep) -> list[AuditEventRead]:
    """The events behind one baseline, or a 404 that says why there are none."""
    recorded = await audit.log_for_baseline(baseline_id)
    if not recorded:
        raise NotFoundError(
            f"No hay ningún evento registrado para la línea base '{baseline_id}'. La bitácora "
            "es append-only: si no hay nada, es que esa línea base no se compuso aquí."
        )
    return [AuditEventRead.model_validate(event) for event in recorded]
