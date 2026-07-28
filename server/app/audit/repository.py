"""UCM-11 - The ledger's only writer. It appends; it has no update path.

The repository owns what the caller must not choose: the position in the ledger
(`sequence`), the instant (`recorded_at`) and the link to the previous event
(`prev_hash`/`event_hash`). A caller can therefore write a wrong justification,
but not a wrong order, a backdated event or an unchained one.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.chain import GENESIS_HASH, event_digest
from app.audit.models import AuditEvent
from app.audit.schemas import AuditEventCreate


class AuditRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def append(self, entry: AuditEventCreate) -> AuditEvent:
        (recorded,) = await self.append_many([entry])
        return recorded

    async def append_many(self, entries: Sequence[AuditEventCreate]) -> list[AuditEvent]:
        """Append a batch in one transaction, chained in the order received.

        A full core run is one batch: either the whole trail of the run is in the
        log or none of it is. A half-written trail would be worse than no trail.
        """
        head = await self.head()
        sequence = head.sequence if head is not None else 0
        prev_hash = head.event_hash if head is not None else GENESIS_HASH

        events: list[AuditEvent] = []
        for entry in entries:
            sequence += 1
            recorded = AuditEvent(
                **entry.model_dump(),
                sequence=sequence,
                recorded_at=datetime.now(UTC),
                prev_hash=prev_hash,
                event_hash="",
            )
            recorded.event_hash = event_digest(recorded)
            prev_hash = recorded.event_hash
            events.append(recorded)

        self.db.add_all(events)
        await self.db.commit()
        return events

    async def head(self) -> AuditEvent | None:
        """The last event of the ledger — where the next one chains onto."""
        result = await self.db.execute(
            select(AuditEvent).order_by(AuditEvent.sequence.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    async def by_run(self, run_id: UUID) -> list[AuditEvent]:
        result = await self.db.execute(
            select(AuditEvent).where(AuditEvent.run_id == run_id).order_by(AuditEvent.sequence)
        )
        return list(result.scalars().all())

    async def trail_for_baseline(self, baseline_id: UUID) -> list[AuditEvent]:
        """Every event of every run that led to a baseline — not only the signed ones.

        `GET /baseline/{id}/audit-log` promises *full* traceability, and the
        engine's decisions are recorded before the baseline exists (they are what
        the human composes from). So the query walks back from the events stamped
        with the baseline to the runs that produced them.
        """
        runs = select(AuditEvent.run_id).where(AuditEvent.baseline_id == baseline_id)
        result = await self.db.execute(
            select(AuditEvent).where(AuditEvent.run_id.in_(runs)).order_by(AuditEvent.sequence)
        )
        return list(result.scalars().all())

    async def all(self) -> list[AuditEvent]:
        """The whole ledger, in order. Used to verify the chain end to end."""
        result = await self.db.execute(select(AuditEvent).order_by(AuditEvent.sequence))
        return list(result.scalars().all())

    async def count(self) -> int:
        result = await self.db.execute(select(func.count()).select_from(AuditEvent))
        return int(result.scalar_one())
