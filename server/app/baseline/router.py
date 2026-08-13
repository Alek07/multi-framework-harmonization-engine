"""UCM-15/16/21/46 - Everything about a baseline: composing it, its trail, the list, the document.

The first two are halves of the same promise. One is where the human composes and
signs; the other is where anyone can check what was signed and why. UCM-15 declared
both contracts; UCM-16 fills the composition in without changing what a client
sends.

The third answers what neither of them can — *what has been signed here?* — for a
caller that has no baseline id. A read over the ledger (`baseline/listing.py`).

The fourth answers a different question again: *what applies to this asset, what
does not, and on whose word?* That is a declaration of applicability, and it is a
document rather than a query — which is why it is served in two spellings, its
own and OSCAL's (`baseline/statement.py`, `baseline/oscal.py`). Like the list, it
is a projection: it computes nothing and stores nothing.

One note on the trail. It is served by baseline id, and it deliberately returns
*more* than the events stamped with that baseline: the engine's decisions are
recorded before a baseline exists — they are what the human composed from — so the
query walks back to the runs those events belong to (`trail_for_baseline`).
Serving only the signed events would be a trail that starts after the interesting
part.
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

# Named `format` on the wire and `document` in the signature: `format` is a Python
# builtin, and shadowing one in a handler is how a subtle bug gets written later.
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
    """The signed baseline as the document a reviewer expects to see (UCM-46).

    One row per required capability and per zone: the decision, the mechanisms
    with their disposition and jurisdiction, the justified exclusions with the
    rule and the premise that fired them, the tier and phase, the gap and its
    residual, and the entries of the ledger that back each row. Projected from the
    trail and from nothing else — it computes nothing, stores nothing, and reports
    the catalog and rules that governed the signature rather than today's.

    `?format=oscal` returns the same content as a partial OSCAL SSP. That branch
    returns a `Response` directly and therefore bypasses `response_model`, which
    is deliberate: OSCAL spells its fields with hyphens and omits what it does not
    know, and neither is true of the declaration's own schema.
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
