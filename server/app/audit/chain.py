"""Tamper-evident chain over the append-only log.

Triggers forbid `UPDATE`/`DELETE` (`models.py`), but that only protects the log
while it is used through the database — anyone with the SQLite file can still
rewrite a row. So every event also carries the SHA-256 digest of its own canonical
form *including the previous event's digest*; re-walking the chain (`verify_chain`)
turns a silent edit into a detectable one.

The digest is computed over the stored values, normalised (enums by value, UUIDs
and timestamps as strings, UTC), so it recomputes to the same value after the row
is read back or received through the API.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import datetime
from enum import Enum
from typing import Any, Protocol
from uuid import UUID

from app.audit.schemas import ChainVerification, as_utc

# `prev_hash` of the first event of the ledger: there is nothing behind it.
GENESIS_HASH = "0" * 64

# Everything that is chained. Adding a field to the model without adding it here
# would leave it outside the digest — i.e. editable without leaving a trace.
CHAINED_FIELDS = (
    "sequence",
    "recorded_at",
    "actor",
    "actor_ref",
    "stage",
    "event_type",
    "run_id",
    "baseline_id",
    "profile_id",
    "zone_id",
    "capability_id",
    "control_id",
    "rule_id",
    "decision",
    "rationale",
    "versions",
    "payload",
    "prev_hash",
)


class ChainedEvent(Protocol):
    """What `verify_chain` needs: the position, the link and the digest."""

    sequence: int
    prev_hash: str
    event_hash: str


def canonical_form(event: Any) -> str:
    """The exact string the digest is taken over. Stable across write and read."""
    fields = {name: _normalise(getattr(event, name)) for name in CHAINED_FIELDS}
    return json.dumps(fields, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def event_digest(event: Any) -> str:
    """SHA-256 of the event's canonical form, `prev_hash` included."""
    return hashlib.sha256(canonical_form(event).encode("utf-8")).hexdigest()


def verify_chain(
    events: Sequence[ChainedEvent], *, expect_genesis: bool = True
) -> ChainVerification:
    """Re-walk the chain and report the first break, if there is one.

    Two independent checks: each event's digest must match its own stored content
    (catches an edited field) and consecutive events must link (catches a removed
    or inserted one). `expect_genesis` is for the whole ledger — it additionally
    demands that the sequence starts at 1 and has no holes. When verifying a
    single run's slice, pass `expect_genesis=False`: the slice legitimately starts
    in the middle of the ledger.
    """
    if not events:
        return ChainVerification(
            valid=True, events=0, detail="La bitácora está vacía: no hay cadena que verificar."
        )

    if expect_genesis:
        first = events[0]
        if first.sequence != 1 or first.prev_hash != GENESIS_HASH:
            return ChainVerification(
                valid=False,
                events=len(events),
                first_broken_sequence=first.sequence,
                detail=(
                    f"La cadena no arranca en el evento génesis: se esperaba sequence=1 con "
                    f"prev_hash={GENESIS_HASH}, se encontró sequence={first.sequence}. "
                    "Falta el principio de la bitácora."
                ),
            )

    previous: ChainedEvent | None = None
    for event in events:
        if event.event_hash != event_digest(event):
            return ChainVerification(
                valid=False,
                events=len(events),
                first_broken_sequence=event.sequence,
                detail=(
                    f"El evento {event.sequence} no coincide con su propio resumen: su contenido "
                    "fue alterado después de registrarse."
                ),
            )
        if previous is not None:
            if expect_genesis and event.sequence != previous.sequence + 1:
                return ChainVerification(
                    valid=False,
                    events=len(events),
                    first_broken_sequence=event.sequence,
                    detail=(
                        f"Hay un hueco en la bitácora entre los eventos {previous.sequence} y "
                        f"{event.sequence}: se eliminó al menos un registro."
                    ),
                )
            if event.sequence == previous.sequence + 1 and event.prev_hash != previous.event_hash:
                return ChainVerification(
                    valid=False,
                    events=len(events),
                    first_broken_sequence=event.sequence,
                    detail=(
                        f"El evento {event.sequence} no enlaza con el {previous.sequence}: la "
                        "cadena se rompió (registro sustituido o insertado)."
                    ),
                )
        previous = event

    return ChainVerification(
        valid=True,
        events=len(events),
        detail=(
            f"Cadena íntegra: {len(events)} evento(s) verificados uno a uno contra su resumen "
            "SHA-256 y contra el evento anterior."
        ),
    )


def _normalise(value: Any) -> Any:
    """Same value in, same JSON out — whatever the driver gave the field back as."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return as_utc(value).isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _normalise(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_normalise(item) for item in value]
    return value
