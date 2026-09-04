"""The ledger in SQLite: append-only, chained, and readable end to end.

Also the M1 gate: the whole deterministic core runs with the two hand-written
profiles (no AI) and every decision ends up in the log — author, reason and
position in a chain that can be re-verified.
"""

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.schemas import AssetProfile
from app.audit.chain import GENESIS_HASH, verify_chain
from app.audit.models import AuditEvent
from app.audit.schemas import (
    AuditActor,
    AuditEventRead,
    AuditEventType,
    AuditStage,
    actor_for,
)
from app.audit.service import AuditService
from app.catalog.schemas import Catalog
from app.engine.schemas import ProfileGating, ProfilePrioritization, ProfileResolution


async def _record_a(
    audit: AuditService,
    profile_a: AssetProfile,
    resolution_a: ProfileResolution,
    gating_a: ProfileGating,
    priorities_a: ProfilePrioritization,
) -> list[AuditEvent]:
    return await audit.record_core_run(profile_a, resolution_a, gating_a, priorities_a, uuid4())


async def test_a_core_run_is_recorded_in_order_with_who_what_why_and_when(
    audit: AuditService,
    profile_a: AssetProfile,
    resolution_a: ProfileResolution,
    gating_a: ProfileGating,
    priorities_a: ProfilePrioritization,
) -> None:
    events = await _record_a(audit, profile_a, resolution_a, gating_a, priorities_a)

    assert [event.sequence for event in events] == list(range(1, len(events) + 1))
    assert events[0].prev_hash == GENESIS_HASH
    for event in events:
        assert event.actor is AuditActor.ENGINE
        assert event.recorded_at is not None
        assert event.rationale.strip()
        assert event.profile_id == "PROFILE-A"
    # Each event links to the one before it.
    for previous, event in zip(events, events[1:], strict=False):
        assert event.prev_hash == previous.event_hash


async def test_the_log_cannot_be_updated(
    audit: AuditService,
    db: AsyncSession,
    profile_a: AssetProfile,
    resolution_a: ProfileResolution,
    gating_a: ProfileGating,
    priorities_a: ProfilePrioritization,
) -> None:
    """Not "the code does not update it": the database refuses the statement."""
    await _record_a(audit, profile_a, resolution_a, gating_a, priorities_a)

    with pytest.raises(DatabaseError, match="append-only"):
        await db.execute(text("UPDATE audit_events SET rationale = 'otra cosa' WHERE sequence = 1"))
    await db.rollback()


async def test_the_log_cannot_be_deleted(
    audit: AuditService,
    db: AsyncSession,
    profile_a: AssetProfile,
    resolution_a: ProfileResolution,
    gating_a: ProfileGating,
    priorities_a: ProfilePrioritization,
) -> None:
    await _record_a(audit, profile_a, resolution_a, gating_a, priorities_a)

    with pytest.raises(DatabaseError, match="append-only"):
        await db.execute(text("DELETE FROM audit_events WHERE sequence = 1"))
    await db.rollback()


async def test_a_blank_justification_is_refused_by_the_table(
    audit: AuditService,
    db: AsyncSession,
    profile_a: AssetProfile,
    resolution_a: ProfileResolution,
    gating_a: ProfileGating,
    priorities_a: ProfilePrioritization,
) -> None:
    """The contract is in the schema too, not only in Pydantic."""
    events = await _record_a(audit, profile_a, resolution_a, gating_a, priorities_a)
    columns = ", ".join(
        [
            "id",
            "sequence",
            "recorded_at",
            "actor",
            "stage",
            "event_type",
            "run_id",
            "profile_id",
            "decision",
            "rationale",
            "versions",
            "payload",
            "prev_hash",
            "event_hash",
        ]
    )
    with pytest.raises(DatabaseError, match="rationale_not_blank"):
        await db.execute(
            text(
                f"INSERT INTO audit_events ({columns}) VALUES "
                "(x'00', :sequence, '2026-07-27 00:00:00', 'engine', 'run', 'run_started', "
                "x'01', 'PROFILE-A', 'sin motivo', '   ', '{}', '{}', :prev, 'deadbeef')"
            ),
            {"sequence": len(events) + 1, "prev": events[-1].event_hash},
        )
    await db.rollback()


async def test_the_chain_survives_a_round_trip_and_detects_a_tampered_event(
    audit: AuditService,
    profile_a: AssetProfile,
    resolution_a: ProfileResolution,
    gating_a: ProfileGating,
    priorities_a: ProfilePrioritization,
) -> None:
    """Whoever receives the log can re-verify it — and catch an edit made around us."""
    await _record_a(audit, profile_a, resolution_a, gating_a, priorities_a)
    assert (await audit.verify_ledger()).valid

    served = [AuditEventRead.model_validate(event) for event in await audit.repository.all()]
    assert verify_chain(served).valid

    served[10].rationale = "una justificación que nadie escribió"
    tampered = verify_chain(served)
    assert not tampered.valid
    assert tampered.first_broken_sequence == served[10].sequence
    assert "alterado" in tampered.detail


async def test_the_chain_detects_a_removed_event(
    audit: AuditService,
    profile_a: AssetProfile,
    resolution_a: ProfileResolution,
    gating_a: ProfileGating,
    priorities_a: ProfilePrioritization,
) -> None:
    await _record_a(audit, profile_a, resolution_a, gating_a, priorities_a)
    served = [AuditEventRead.model_validate(event) for event in await audit.repository.all()]

    without_one = served[:5] + served[6:]
    broken = verify_chain(without_one)
    assert not broken.valid
    assert broken.first_broken_sequence == served[6].sequence
    assert "hueco" in broken.detail


async def test_appending_never_rewrites_what_is_already_there(
    audit: AuditService,
    profile_a: AssetProfile,
    resolution_a: ProfileResolution,
    gating_a: ProfileGating,
    priorities_a: ProfilePrioritization,
    profile_b: AssetProfile,
    resolution_b: ProfileResolution,
    gating_b: ProfileGating,
    priorities_b: ProfilePrioritization,
) -> None:
    first = await _record_a(audit, profile_a, resolution_a, gating_a, priorities_a)
    before = {event.sequence: event.event_hash for event in first}

    await audit.record_core_run(profile_b, resolution_b, gating_b, priorities_b, uuid4())

    after = {event.sequence: event.event_hash for event in await audit.repository.all()}
    assert all(after[sequence] == digest for sequence, digest in before.items())
    assert len(after) > len(before)
    assert (await audit.verify_ledger()).valid


async def test_two_runs_stay_separable_and_each_verifies_on_its_own(
    audit: AuditService,
    profile_a: AssetProfile,
    resolution_a: ProfileResolution,
    gating_a: ProfileGating,
    priorities_a: ProfilePrioritization,
    profile_b: AssetProfile,
    resolution_b: ProfileResolution,
    gating_b: ProfileGating,
    priorities_b: ProfilePrioritization,
) -> None:
    run_a, run_b = uuid4(), uuid4()
    await audit.record_core_run(profile_a, resolution_a, gating_a, priorities_a, run_a)
    await audit.record_core_run(profile_b, resolution_b, gating_b, priorities_b, run_b)

    log_a = await audit.log_for_run(run_a)
    log_b = await audit.log_for_run(run_b)
    assert {event.profile_id for event in log_a} == {"PROFILE-A"}
    assert {event.profile_id for event in log_b} == {"PROFILE-B"}
    # The second run starts where the first one ended: one ledger, two trails.
    assert log_b[0].sequence == log_a[-1].sequence + 1
    assert (await audit.verify_run(run_b)).valid


async def test_the_human_decisions_are_recorded_on_top_of_the_engine_run(
    audit: AuditService,
    profile_a: AssetProfile,
    resolution_a: ProfileResolution,
    gating_a: ProfileGating,
    priorities_a: ProfilePrioritization,
) -> None:
    """Sovereign composition: the operator chooses, and the choice is on the record."""
    run_id = uuid4()
    engine_events = await audit.record_core_run(
        profile_a, resolution_a, gating_a, priorities_a, run_id
    )
    baseline_id = uuid4()

    choice = await audit.record_human_decision(
        run_id=run_id,
        profile_id=profile_a.id,
        event_type=AuditEventType.OPTION_SELECTED,
        decision="Se elige IEC62443 para el corredor OT frente al equivalente NIST",
        rationale="La zona es OT y el operador asume la precedencia ICS para el corredor.",
        operator="operador.ot@acp",
        zone_id="Z-OT-CORRIDOR",
    )
    signature = await audit.record_human_decision(
        run_id=run_id,
        profile_id=profile_a.id,
        event_type=AuditEventType.BASELINE_SIGNED,
        stage=AuditStage.SIGNATURE,
        baseline_id=baseline_id,
        decision="Baseline compuesta y firmada para PROFILE-A",
        rationale="Bloque obligatorio cerrado con los compensatorios declarados.",
        operator="operador.ot@acp",
    )

    assert choice.actor is AuditActor.HUMAN
    assert choice.actor_ref == "operador.ot@acp"
    assert signature.sequence == choice.sequence + 1

    # `GET /baseline/{id}/audit-log` promises the *full* trail: the engine's run
    # included, even though it happened before the baseline existed.
    trail = await audit.log_for_baseline(baseline_id)
    assert len(trail) == len(engine_events) + 2
    assert trail[0].event_type is AuditEventType.RUN_STARTED
    assert trail[-1].event_type is AuditEventType.BASELINE_SIGNED
    assert verify_chain(trail, expect_genesis=False).valid


async def test_ratifying_a_mechanism_is_a_human_act_and_not_a_selection(
    audit: AuditService, profile_a: AssetProfile
) -> None:
    """Accepting the engine's retained mechanism has its own event type.

    It belongs to the human (nobody else can ratify) and is deliberately not
    `OPTION_SELECTED`: in the trail, "eligió SR 2.8 frente a CIS 8.2" and
    "ratificó lo que el motor retuvo" have to stay different sentences.
    """
    ratified = await audit.record_human_decision(
        run_id=uuid4(),
        profile_id=profile_a.id,
        event_type=AuditEventType.MECHANISM_RATIFIED,
        decision="Ratificado el mecanismo retenido para «Segmentación» en Z-OT-CORRIDOR",
        rationale="No hubo elección entre equivalentes: la firma asume lo que el motor retuvo.",
        operator="operador.ot@acp",
        zone_id="Z-OT-CORRIDOR",
    )

    assert ratified.actor is AuditActor.HUMAN
    assert ratified.event_type is not AuditEventType.OPTION_SELECTED
    assert actor_for(AuditEventType.MECHANISM_RATIFIED) is AuditActor.HUMAN


async def test_only_a_human_event_type_can_be_a_human_decision(
    audit: AuditService, profile_a: AssetProfile
) -> None:
    with pytest.raises(ValueError, match="not a human decision"):
        await audit.record_human_decision(
            run_id=uuid4(),
            profile_id=profile_a.id,
            event_type=AuditEventType.MECHANISM_EXCLUDED,
            decision="…",
            rationale="…",
            operator="operador.ot@acp",
        )


async def test_the_whole_core_of_both_profiles_is_traceable_end_to_end(
    audit: AuditService,
    catalog: Catalog,
    profile_a: AssetProfile,
    resolution_a: ProfileResolution,
    gating_a: ProfileGating,
    priorities_a: ProfilePrioritization,
    profile_b: AssetProfile,
    resolution_b: ProfileResolution,
    gating_b: ProfileGating,
    priorities_b: ProfilePrioritization,
) -> None:
    """M1 gate: the two hand-written profiles, no AI, everything on the record."""
    run_a, run_b = uuid4(), uuid4()
    await audit.record_core_run(profile_a, resolution_a, gating_a, priorities_a, run_a)
    await audit.record_core_run(profile_b, resolution_b, gating_b, priorities_b, run_b)

    events = await audit.repository.all()
    assert await audit.repository.count() == len(events)
    assert (await audit.verify_ledger()).valid

    zones = [zone.id for zone in profile_a.zones] + [zone.id for zone in profile_b.zones]
    accounted = {
        (event.zone_id, event.capability_id)
        for event in events
        if event.event_type is AuditEventType.CAPABILITY_MAPPED
    }
    assert accounted == {
        (zone_id, capability.id) for zone_id in zones for capability in catalog.capabilities
    }

    stages = {event.stage for event in events}
    assert stages == {
        AuditStage.RUN,
        AuditStage.MAPPING,
        AuditStage.CONFLICT_RESOLUTION,
        AuditStage.GATING,
        AuditStage.PRIORITIZATION,
    }
