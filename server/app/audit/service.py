"""UCM-11 - The log's use cases: record, read back, verify.

Two authors write here and the service keeps them apart on purpose:

* **The engine** writes a whole run at once (`record_core_run`), derived from what
  the deterministic core already decided (`trail.py`). It never recomputes the
  core: it receives the resolution, the gating and the prioritisation of *one*
  run and refuses to log a trail stitched from different ones.
* **The human** writes one decision at a time (`record_human_decision`) while
  composing and signing the baseline (UCM-16). Every one of them demands a
  written justification — that is the whole point of a sovereign composition:
  not that the operator can choose, but that the choice is on the record.

Reading is by run (`log_for_run`) or by baseline (`log_for_baseline`, what
`GET /baseline/{id}/audit-log` will serve). Verification (`verify_ledger`) re-walks
the hash chain: the log does not only claim to be append-only, it can show it.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from app.assets.schemas import AssetProfile
from app.audit.chain import verify_chain
from app.audit.models import AuditEvent
from app.audit.repository import AuditRepository
from app.audit.schemas import (
    HUMAN_EVENT_TYPES,
    AuditActor,
    AuditEventCreate,
    AuditEventType,
    AuditStage,
    ChainVerification,
)
from app.audit.trail import trail_for_core_run
from app.engine.schemas import ProfileGating, ProfilePrioritization, ProfileResolution
from app.retrieval.schemas import ProfileRetrieval
from app.retrieval.trail import trail_for_retrieval


class AuditService:
    """Append-only by construction: there is no method here that rewrites an event."""

    def __init__(self, repository: AuditRepository):
        self.repository = repository

    async def record(self, entry: AuditEventCreate) -> AuditEvent:
        return await self.repository.append(entry)

    async def record_core_run(
        self,
        profile: AssetProfile,
        resolution: ProfileResolution,
        gating: ProfileGating,
        prioritization: ProfilePrioritization,
        run_id: UUID | None = None,
    ) -> list[AuditEvent]:
        """Record every decision of one core run, in pipeline order.

        Returns the persisted events; `run_id` (generated if not given) is the
        handle the human's later decisions and the signed baseline hang from.
        """
        run_id = run_id if run_id is not None else uuid4()
        entries = trail_for_core_run(profile, resolution, gating, prioritization, run_id)
        return await self.repository.append_many(entries)

    async def record_retrieval(
        self, retrieval: ProfileRetrieval, run_id: UUID | None = None
    ) -> list[AuditEvent]:
        """Record the RAG pass of one run (UCM-13): what it added, and to what.

        Kept apart from `record_core_run` because the pass is optional — the core
        runs without it and the baseline is composable without it — but it is
        still the engine's own entry: retrieval offers options, it never decides.
        The `run_id` is the core run's, so the log reads as one story.
        """
        run_id = run_id if run_id is not None else uuid4()
        return await self.repository.append_many(trail_for_retrieval(retrieval, run_id))

    async def record_human_decision(
        self,
        *,
        run_id: UUID,
        profile_id: str,
        event_type: AuditEventType,
        decision: str,
        rationale: str,
        operator: str,
        stage: AuditStage = AuditStage.COMPOSITION,
        baseline_id: UUID | None = None,
        zone_id: str | None = None,
        capability_id: str | None = None,
        control_id: str | None = None,
        versions: dict[str, str] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> AuditEvent:
        """Record a decision of the operator: their choice, and why they made it.

        `event_type` has to be one of the human's — the composition cannot be
        signed off as if the engine had decided it.
        """
        if event_type not in HUMAN_EVENT_TYPES:
            raise ValueError(f"'{event_type.value}' is not a human decision")

        return await self.repository.append(
            AuditEventCreate(
                actor=AuditActor.HUMAN,
                actor_ref=operator,
                stage=stage,
                event_type=event_type,
                run_id=run_id,
                baseline_id=baseline_id,
                profile_id=profile_id,
                zone_id=zone_id,
                capability_id=capability_id,
                control_id=control_id,
                decision=decision,
                rationale=rationale,
                versions=versions or {},
                payload=payload or {},
            )
        )

    async def log_for_run(self, run_id: UUID) -> list[AuditEvent]:
        return await self.repository.by_run(run_id)

    async def log_for_baseline(self, baseline_id: UUID) -> list[AuditEvent]:
        """The full trail behind a baseline: the engine's run *and* the human's choices."""
        return await self.repository.trail_for_baseline(baseline_id)

    async def verify_ledger(self) -> ChainVerification:
        """Re-walk the whole chain: no edited field, no missing event."""
        return verify_chain(await self.repository.all())

    async def verify_run(self, run_id: UUID) -> ChainVerification:
        """Verify one run's slice. It starts mid-ledger, so genesis is not expected."""
        return verify_chain(await self.repository.by_run(run_id), expect_genesis=False)

    async def verify_baseline(self, baseline_id: UUID) -> ChainVerification:
        """Verify the slice behind one baseline — what `GET /baseline/{id}/audit-log` serves.

        The endpoint promises *full traceability*, and a list of events is only
        worth that promise if it can be checked. Same reading as `verify_run`: the
        slice starts wherever that baseline's first run started, so genesis is not
        expected. A slice that skips a sequence number is not a break either — the
        ledger interleaves runs — so what is verified here is each event's own
        digest and its link to the event it was written after.
        """
        return verify_chain(
            await self.repository.trail_for_baseline(baseline_id), expect_genesis=False
        )
