"""The list of signed baselines, projected from the ledger and from nothing else.

`GET /baselines` is the sixth endpoint, and it is the one place in the system that
answers a question none of the other five can: *what has been signed here?* The
composition endpoint hands a baseline back to whoever signed it and the trail
endpoint serves one by id — both of which assume the caller already knows the id.
A client that was closed and reopened does not, and reconstructing the list from
whatever the browser happened to keep would make the record depend on the machine
that was in front of it.

What it deliberately does **not** do is introduce a second place where a baseline
lives. There is no `baselines` table. A signed baseline already exists in the
ledger as its `baseline_signed` entry — actor, instant, profile, versions and the
payload the composition wrote — and this module reads that entry back. Invariant 5
is untouched: still one mutable state, still append-only, still no copy that can
disagree with the trail.

The projection is a pure function of the events for the same reason the trail
writers are: the same ledger always produces the same list, so the list can be
asserted on directly (`tests/api/test_baselines.py`).
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

    The payload is read defensively — `.get` with a default rather than a subscript
    — because the ledger is append-only in the strongest sense: entries written by
    an earlier version of the trail writer cannot be migrated to carry a field a
    later one added. A summary of an old baseline should be poorer, never a 500.
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
        # The signer is the actor of their own entry. There is no separate name
        # field to disagree with it.
        signed_by=signed.actor_ref or "",
        # Read back as aware UTC, the same way `AuditEventRead` does it. SQLite
        # drops the offset, and a naive timestamp on the wire is one the browser
        # reads as local time — which would date a signature wrong by up to a day
        # and make the list disagree with the compose response about the same
        # baseline.
        signed_at=as_utc(signed.recorded_at),
        versions=dict(signed.versions or {}),
        zone_ids=_strings(payload, "zones"),
        tier_0_complete=bool(payload.get("tier_0_complete", False)),
        closed_mandates=_mandates(payload),
        human_choices=_count(payload, "human_choices"),
        ratified_mandates=_count(payload, "ratified_mandates"),
        # Counted over the entries rather than taken from the payload: these two are
        # what the operator did, and the entries that record each of them are the
        # evidence for it. A tally written by the same hand it describes proves less.
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
