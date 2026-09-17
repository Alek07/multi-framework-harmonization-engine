"""The `audit_events` table: the only mutable state of the system.

Mutable in one direction only. Three layers hold the append-only invariant:

1. **The schema**: no `updated_at`, `CHECK`s that refuse a blank `decision` or
   `rationale` and a non-positive `sequence`.
2. **The database**: `BEFORE UPDATE` / `BEFORE DELETE` triggers that abort the
   statement, so an `UPDATE` cannot be issued even by hand through the driver.
3. **The chain**: `prev_hash`/`event_hash` (`chain.py`) make an edit made straight
   on the SQLite file detectable.

The repository is the only writer and it has no update path (`repository.py`).
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    DDL,
    JSON,
    CheckConstraint,
    DateTime,
    Integer,
    String,
    Text,
    Uuid,
    event,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.audit.schemas import AuditActor, AuditEventType, AuditStage
from app.models.base import Base, UUIDPKMixin


def _enum(python_enum: type[enum.Enum], name: str) -> SAEnum:
    """Store the enum's *value* (`engine`), not its member name (`ENGINE`).

    Rendered as a `VARCHAR` + `CHECK`: the log stays readable with any SQLite
    client, which matters for an annex the tutors have to be able to open.
    """
    return SAEnum(
        python_enum,
        name=name,
        native_enum=False,
        length=32,
        values_callable=lambda members: [member.value for member in members],
    )


class AuditEvent(Base, UUIDPKMixin):
    """One decision — engine's or human's — with who, what, why and when."""

    __tablename__ = "audit_events"

    __table_args__ = (
        CheckConstraint("sequence > 0", name="ck_audit_events_sequence_positive"),
        CheckConstraint("length(trim(decision)) > 0", name="ck_audit_events_decision_not_blank"),
        CheckConstraint("length(trim(rationale)) > 0", name="ck_audit_events_rationale_not_blank"),
    )

    # Position in the ledger. Unique: a race that tried to fork the chain fails
    # loudly instead of writing two events at the same link.
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, unique=True, index=True)
    # Stamped by the ledger in UTC. SQLite drops the offset on read; `as_utc`
    # puts it back, which is what keeps the digest verifiable.
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    actor: Mapped[AuditActor] = mapped_column(
        _enum(AuditActor, "audit_actor"), nullable=False, index=True
    )
    actor_ref: Mapped[str | None] = mapped_column(String(120))
    stage: Mapped[AuditStage] = mapped_column(
        _enum(AuditStage, "audit_stage"), nullable=False, index=True
    )
    event_type: Mapped[AuditEventType] = mapped_column(
        _enum(AuditEventType, "audit_event_type"), nullable=False, index=True
    )

    run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    baseline_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    profile_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    zone_id: Mapped[str | None] = mapped_column(String(64), index=True)
    capability_id: Mapped[str | None] = mapped_column(String(64), index=True)
    control_id: Mapped[str | None] = mapped_column(String(64), index=True)
    rule_id: Mapped[str | None] = mapped_column(String(64))

    decision: Mapped[str] = mapped_column(String(500), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    versions: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    event_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    def __repr__(self) -> str:
        return (
            f"AuditEvent(sequence={self.sequence}, actor={self.actor.value}, "
            f"event_type={self.event_type.value}, profile_id={self.profile_id!r})"
        )


def _register_append_only_guards() -> None:
    """Refuse `UPDATE`/`DELETE` at the database level, not just in the code."""
    for operation in ("UPDATE", "DELETE"):
        trigger = (
            f"CREATE TRIGGER IF NOT EXISTS audit_events_no_{operation.lower()} "
            f"BEFORE {operation} ON audit_events BEGIN "
            f"SELECT RAISE(ABORT, 'audit_events is append-only: "
            f"{operation} is not allowed'); END"
        )
        event.listen(
            AuditEvent.__table__,
            "after_create",
            DDL(trigger).execute_if(dialect="sqlite"),
        )


_register_append_only_guards()
