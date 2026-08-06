/**
 * Etapa 5 — the trail.
 *
 * Before the signature this table shows the operator's *pending* decisions,
 * hatched and italic, with the timestamp column empty: nothing has been recorded
 * yet, and a preview that looked like the ledger would be a lie about when a
 * decision became a fact. After it, the same table is the server's own record —
 * engine entries and human ones, in ledger order, with the re-walk of the hash
 * chain underneath.
 *
 * There is no edit action and no delete action anywhere in it, not even a
 * disabled one. The log is append-only, and the screen says that in words the
 * operator can act on rather than by naming the invariant.
 */

import { useState } from 'react'

import type { AuditActor, AuditEventType } from '../../api/types'
import { ACTOR, AUDIT_EVENT, fieldLabel } from '../../lib/labels'
import { usePage } from '../../lib/paging'
import { useComposition } from '../../state/composition'
import { Hint, Notice, Pager, Section } from '../ui'

const COLUMNS = '34px 150px 74px 210px 1fr 1fr'

/** How many entries are readable at once. */
const PER_PAGE = 10

/** One line of the trail, whether it is already recorded or still pending. */
interface Row {
  n: string
  when: string
  actor: AuditActor
  event: string
  /** The raw event type, for the tooltip and the test hook — never on screen. */
  raw: string
  what: string
  why: string
  key: string
}

function Header() {
  return (
    <div
      className="grid gap-0 bg-line-3 px-3 py-2 text-[10.5px] font-semibold text-ink-2"
      style={{ gridTemplateColumns: COLUMNS }}
    >
      <span>Nº</span>
      <span>Cuándo</span>
      <span>Quién</span>
      <span>Qué ocurrió</span>
      <span>Sobre qué</span>
      <span>Por qué</span>
    </div>
  )
}

const FILTERS: { value: 'todos' | AuditActor; label: string; note: string }[] = [
  { value: 'todos', label: 'Todo', note: 'Todas las anotaciones, en orden' },
  {
    value: 'engine',
    label: 'Lo que hizo el sistema',
    note: 'Cálculos y reglas aplicadas automáticamente',
  },
  {
    value: 'human',
    label: 'Lo que decidiste tú',
    note: 'Elecciones, descartes y aceptaciones firmadas por una persona',
  },
]

export function StageAudit() {
  const { auditLog, auditLogError, choices, corrections, signed } = useComposition()
  const [filter, setFilter] = useState<'todos' | AuditActor>('todos')

  const pending = [
    ...corrections.map((correction) => ({
      actor: 'human' as const,
      event: 'corrección de la ficha del activo',
      raw: 'profile.correction',
      what: `${fieldLabel(correction.path)}: ${correction.from} → ${correction.to}`,
      why: 'Corrección tuya sobre lo que el asistente había entendido',
    })),
    ...choices.map((choice) => ({
      actor: 'human' as const,
      event: AUDIT_EVENT[choice.kind as AuditEventType] ?? choice.kind,
      raw: choice.kind,
      what: `${choice.capability_id} · zona ${choice.zone_id}${
        choice.control_id ? ` · ${choice.control_id}` : ''
      }`,
      why: choice.rationale,
    })),
  ]

  const rows: Row[] = signed
    ? (auditLog?.events ?? [])
        .filter((event) => filter === 'todos' || event.actor === filter)
        .map((event, index) => ({
          n: String(event.sequence).padStart(2, '0'),
          when: event.recorded_at.replace('T', ' ').slice(0, 19),
          actor: event.actor,
          event: AUDIT_EVENT[event.event_type] ?? event.event_type,
          raw: event.event_type,
          what: event.decision,
          why: event.rationale,
          key: `${event.id}-${index}`,
        }))
    : pending
        .filter((row) => filter === 'todos' || row.actor === filter)
        .map((row, index) => ({
          n: String(index + 1).padStart(2, '0'),
          when: 'sin registrar',
          actor: row.actor,
          event: row.event,
          raw: row.raw,
          what: row.what,
          why: row.why,
          key: `pending-${index}`,
        }))

  // The numbers in the first column are the ledger's own `sequence`, so page 2
  // starts at 11 and not at 01: the reader is looking at part of one record,
  // not at a record of its own.
  const page = usePage(rows, PER_PAGE, `${filter}-${signed}`)

  return (
    <Section
      id="s6"
      step={5}
      title="Registro de decisiones"
      hint={
        signed
          ? 'Historial completo y definitivo de esta línea base: qué calculó el sistema, qué decidiste tú, cuándo y por qué. No se puede modificar ni borrar, y el propio sistema comprueba que nadie lo haya alterado.'
          : 'Vista previa de lo que se registrará cuando firmes. Todavía no se ha guardado nada: por eso las filas aparecen sombreadas y sin fecha.'
      }
      scope={signed ? 'registro definitivo' : 'aún sin registrar'}
    >
      {signed && auditLog ? (
        <div className="mb-3.5">
          <Notice tone={auditLog.chain.valid ? 'ok' : 'alert'}>
            {auditLog.chain.valid
              ? 'Registro íntegro: se ha comprobado que ninguna anotación ha sido modificada ni eliminada.'
              : 'Atención: la comprobación de integridad del registro ha fallado.'}{' '}
            Contiene {auditLog.engine_events} anotación(es) del sistema y {auditLog.human_events}{' '}
            tuyas.
            <span className="ml-1 text-[11.5px] opacity-80" title={auditLog.chain.detail}>
              (detalle técnico disponible al pasar el ratón)
            </span>
          </Notice>
        </div>
      ) : null}

      {auditLogError ? (
        <div className="mb-3.5">
          <Notice tone="alert" label="NO SE PUDO LEER EL REGISTRO">
            {auditLogError}
          </Notice>
        </div>
      ) : null}

      <div className="my-2.5 mb-3.5 flex flex-wrap gap-1.5">
        {FILTERS.map((option) => (
          <button
            key={option.value}
            type="button"
            title={option.note}
            onClick={() => setFilter(option.value)}
            className={`cursor-pointer rounded-[5px] border px-3 py-[5px] text-[11.5px] font-semibold ${
              filter === option.value
                ? 'border-accent bg-accent-tint text-accent'
                : 'border-line bg-surface-2 text-ink-3'
            }`}
          >
            {option.label}
          </button>
        ))}
      </div>

      <div className="overflow-hidden rounded-md border border-line-2 text-xs leading-[1.5]">
        <Header />
        {rows.length === 0 ? (
          <div className="px-3 py-3 text-[11px] text-ink-4">
            Todavía no has tomado ninguna decisión que registrar.
          </div>
        ) : null}
        {page.slice.map((row) => (
          <div
            key={row.key}
            data-testid="audit-row"
            data-actor={row.actor}
            data-event={row.raw}
            className={`grid border-t border-line-3 px-3 py-[7px] text-[11px] ${
              signed
                ? ''
                : 'bg-[repeating-linear-gradient(45deg,#fdfcfa,#fdfcfa_8px,#faf8f3_8px,#faf8f3_16px)] text-ink-4 italic'
            }`}
            style={{ gridTemplateColumns: COLUMNS }}
          >
            <span className="font-mono text-ink-4">{row.n}</span>
            <span className="font-mono text-ink-3">{row.when}</span>
            <span
              className={`font-semibold ${row.actor === 'engine' ? 'text-defer' : 'text-[#1d6f4c]'}`}
            >
              {ACTOR[row.actor]}
            </span>
            <span title={row.raw}>{row.event}</span>
            <span className={signed ? 'text-ink' : ''}>{row.what}</span>
            <span className="text-ink-3">{row.why}</span>
          </div>
        ))}
      </div>

      <Pager
        page={page.page}
        pages={page.pages}
        from={page.from}
        to={page.to}
        total={page.total}
        noun="anotaciones"
        onPage={page.setPage}
      />

      <Hint className="mt-2">
        Este registro solo admite añadir. No hay ninguna forma de editar ni de borrar una anotación
        —ni siquiera deshabilitada— porque un historial que se puede corregir no sirve como prueba
        ante un auditor.
      </Hint>
    </Section>
  )
}
