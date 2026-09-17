"""`GET /baselines`: signed baselines projected from the ledger, and nothing else.

A signed baseline *is* its `baseline_signed` entry, so there is no table and no
second place one can live.
"""

from __future__ import annotations

from collections import Counter
from typing import Any
from uuid import UUID

from app.audit.models import AuditEvent
from app.audit.schemas import AuditEventType, as_utc
from app.baseline.schemas import BaselineList, BaselineSummary
from app.core.config import settings


def _strings(payload: dict[str, Any], key: str) -> list[str]:
    value = payload.get(key)
    return [str(item) for item in value] if isinstance(value, list) else []


def _mandates(payload: dict[str, Any]) -> dict[str, list[str]]:
    value = payload.get("closed_mandates")
    if not isinstance(value, dict):
        return {}
    return {str(zone): [str(item) for item in ids] for zone, ids in value.items() if ids}


def _count(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    return int(value) if isinstance(value, int) else 0


def summary_of(signed: AuditEvent, counts: Counter[AuditEventType]) -> BaselineSummary:
    """One `baseline_signed` entry, read as the baseline it closed.

    The payload is read with `.get`: an entry written before a field existed cannot
    be migrated, so an old baseline gives a poorer summary rather than a 500.
    """
    payload = signed.payload or {}
    baseline_id = signed.baseline_id
    if baseline_id is None:  # pragma: no cover - a signature always names its baseline
        raise ValueError(f"signature at sequence {signed.sequence} names no baseline")

    return BaselineSummary(
        baseline_id=baseline_id,
        run_id=signed.run_id,
        profile_id=signed.profile_id,
        profile_name=str(payload.get("profile_name") or signed.profile_id),
        # The signer is the actor of their own entry.
        signed_by=signed.actor_ref or "",
        # SQLite drops the offset; naive on the wire is read as local time.
        signed_at=as_utc(signed.recorded_at),
        versions=dict(signed.versions or {}),
        zone_ids=_strings(payload, "zones"),
        tier_0_complete=bool(payload.get("tier_0_complete", False)),
        closed_mandates=_mandates(payload),
        human_choices=_count(payload, "human_choices"),
        ratified_mandates=_count(payload, "ratified_mandates"),
        # Counted over the entries, not taken from a tally the same composition wrote.
        gaps_accepted=counts.get(AuditEventType.GAP_ACCEPTED, 0),
        conflicts_resolved=counts.get(AuditEventType.OPTION_REJECTED, 0),
        audit_events=sum(counts.values()),
        audit_log_path=f"{settings.API_V1_PREFIX}/baseline/{baseline_id}/audit-log",
        signature_rationale=signed.rationale,
    )


def listing_of(
    signatures: list[AuditEvent], counts: dict[UUID, Counter[AuditEventType]]
) -> BaselineList:
    """Every signature the ledger holds, in the order it holds them."""
    baselines = [
        summary_of(signed, counts.get(signed.baseline_id, Counter()))
        for signed in signatures
        if signed.baseline_id is not None
    ]

    return BaselineList(
        baselines=baselines,
        total=len(baselines),
        rationale=(
            f"{len(baselines)} línea(s) base firmada(s) en esta bitácora, de la más reciente a la "
            "más antigua. La lista se lee de la propia bitácora — cada línea base es su entrada "
            "de firma — así que no hay ninguna copia que pueda contradecir la traza: lo que "
            "aparece aquí es exactamente lo que se firmó, y en «bitácora» está el detalle de "
            "cada una."
        )
        if baselines
        else (
            "Todavía no se ha firmado ninguna línea base en esta bitácora. No es un fallo de "
            "lectura: la bitácora es append-only y no contiene ninguna firma."
        ),
    )
