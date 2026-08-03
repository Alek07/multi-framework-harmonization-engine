/**
 * Etapa 5 — the trail.
 *
 * Before the signature this table shows the operator's *pending* decisions,
 * hatched and italic, with the timestamp column empty: nothing has been recorded
 * yet, and a preview that looked like the ledger would be a lie about when a
 * decision became a fact. After it, the same table is the server's answer to
 * `GET /baseline/{id}/audit-log` — engine entries and human ones, in ledger
 * order, with the re-walk of the hash chain underneath.
 *
 * There is no edit action and no delete action anywhere in it, not even a
 * disabled one. The log is append-only (invariant 5).
 */

import { useState } from 'react'

import type { AuditActor } from '../../api/types'
import { useComposition } from '../../state/composition'
import { Notice, Section } from '../ui'

const COLUMNS = '34px 168px 66px 190px 1fr 1fr'

function Header() {
  return (
    <div
      className="grid gap-0 bg-line-3 px-3 py-2 text-[10.5px] font-semibold text-ink-2"
      style={{ gridTemplateColumns: COLUMNS }}
    >
      <span>#</span>
      <span>cuándo</span>
      <span>actor</span>
      <span>evento</span>
      <span>qué</span>
      <span>por qué</span>
    </div>
  )
}

export function StageAudit() {
  const { auditLog, auditLogError, baseline, choices, corrections, signed } = useComposition()
  const [filter, setFilter] = useState<'todos' | AuditActor>('todos')

  const pending = [
    ...corrections.map((correction) => ({
      actor: 'human' as const,
      event: 'profile.correction',
      what: `${correction.path}: ${correction.from} → ${correction.to}`,
      why: 'corrección del operador sobre el borrador del modelo',
    })),
    ...choices.map((choice) => ({
      actor: 'human' as const,
      event: choice.kind,
      what: `${choice.capability_id} @ ${choice.zone_id}${
        choice.control_id ? `: ${choice.control_id}` : ''
      }`,
      why: choice.rationale,
    })),
  ]

  const rows = signed
    ? (auditLog?.events ?? [])
        .filter((event) => filter === 'todos' || event.actor === filter)
        .map((event, index) => ({
          n: String(event.sequence).padStart(2, '0'),
          when: event.recorded_at.replace('T', ' ').slice(0, 19),
          actor: event.actor,
          event: event.event_type,
          what: event.decision,
          why: event.rationale,
          key: `${event.id}-${index}`,
        }))
    : pending
        .filter((row) => filter === 'todos' || row.actor === filter)
        .map((row, index) => ({
          n: String(index + 1).padStart(2, '0'),
          when: '—',
          actor: row.actor,
          event: row.event,
          what: row.what,
          why: row.why,
          key: `pending-${index}`,
        }))

  return (
    <Section
      id="s6"
      step={5}
      title="Bitácora"
      scope={
        signed && baseline
          ? `GET /baseline/${baseline.baseline_id.slice(0, 8)}…/audit-log — respuesta del servidor`
          : 'estado local — aún no registrado; se escribirá al firmar'
      }
    >
      {signed && auditLog ? (
        <div className="mb-3.5">
          <Notice tone={auditLog.chain.valid ? 'ok' : 'alert'}>
            {auditLog.chain.detail} · {auditLog.engine_events} evento(s) del motor ·{' '}
            {auditLog.human_events} del humano.
          </Notice>
        </div>
      ) : null}

      {auditLogError ? (
        <div className="mb-3.5">
          <Notice tone="alert" label="BITÁCORA">
            {auditLogError}
          </Notice>
        </div>
      ) : null}

      <div className="my-2.5 mb-3.5 flex gap-1.5">
        {(['todos', 'engine', 'human'] as const).map((option) => (
          <button
            key={option}
            type="button"
            onClick={() => setFilter(option)}
            className={`cursor-pointer rounded-[5px] border px-3 py-[5px] font-mono text-[11px] font-semibold ${
              filter === option
                ? 'border-accent bg-accent-tint text-accent'
                : 'border-line bg-surface-2 text-ink-3'
            }`}
          >
            {option}
          </button>
        ))}
      </div>

      <div className="overflow-hidden rounded-md border border-line-2 font-mono text-xs leading-[1.5]">
        <Header />
        {rows.length === 0 ? (
          <div className="px-3 py-3 text-[11px] text-ink-4">
            Todavía no hay ninguna decisión que registrar.
          </div>
        ) : null}
        {rows.map((row) => (
          <div
            key={row.key}
            data-testid="audit-row"
            data-actor={row.actor}
            data-event={row.event}
            className={`grid border-t border-line-3 px-3 py-[7px] text-[11px] ${
              signed
                ? ''
                : 'bg-[repeating-linear-gradient(45deg,#fdfcfa,#fdfcfa_8px,#faf8f3_8px,#faf8f3_16px)] text-ink-4 italic'
            }`}
            style={{ gridTemplateColumns: COLUMNS }}
          >
            <span className="text-ink-4">{row.n}</span>
            <span className="text-ink-3">{row.when}</span>
            <span
              className={`font-semibold ${row.actor === 'engine' ? 'text-defer' : 'text-[#1d6f4c]'}`}
            >
              {row.actor}
            </span>
            <span>{row.event}</span>
            <span className={signed ? 'text-ink' : ''}>{row.what}</span>
            <span className="text-ink-3">{row.why}</span>
          </div>
        ))}
      </div>

      <div className="mt-2 text-[11.5px] text-ink-4">
        Append-only: la tabla no tiene acciones de edición ni de borrado — ni siquiera
        deshabilitadas.
      </div>
    </Section>
  )
}
