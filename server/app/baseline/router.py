"""UCM-15 - `POST /baseline/compose` and `GET /baseline/{id}/audit-log`.

Two halves of the same promise. The first is where the human composes and signs;
the second is where anyone can check what was signed and why. The composition
logic is UCM-16's — this ticket declares its contract and answers 501 — while the
trail endpoint works today, because the ledger it reads has existed since UCM-11.

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

from app.api.deps import AuditDep
from app.audit.schemas import AuditActor, AuditEventRead
from app.baseline.schemas import BaselineAuditLog, ComposedBaseline, ComposeRequest
from app.core.exceptions import NotFoundError, NotImplementedYetError
from app.core.schemas import Message

router = APIRouter(prefix="/baseline", tags=["baseline"])

COMPOSE_PENDING = (
    "La composición soberana (elección lado a lado + firma) se implementa en UCM-16. El "
    "contrato de esta petición es firme y ya se valida: lo que falta es la lógica, no el "
    "endpoint. La superficie de la API sigue cerrada en cinco endpoints."
)


@router.post(
    "/compose",
    response_model=ComposedBaseline,
    status_code=status.HTTP_201_CREATED,
    summary="Elecciones del humano → línea base firmada",
    responses={
        422: {"model": Message, "description": "Elecciones o firma inválidas."},
        501: {"model": Message, "description": "Pendiente de UCM-16 (contrato ya validado)."},
    },
)
async def compose_baseline(request: ComposeRequest) -> ComposedBaseline:
    """Record every choice, verify Tier 0 is complete, and sign the baseline (UCM-16).

    FastAPI validates `request` before this body runs, so the contract is already
    doing its job: a malformed composition is rejected with 422 and a well-formed
    one reaches 501. UCM-16 adds the ledger dependency and the logic; it does not
    get to change the shape of what a client sends.
    """
    raise NotImplementedYetError(COMPOSE_PENDING)


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
