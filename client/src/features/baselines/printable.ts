/**
 * The signed baseline as a printable declaration of applicability. Prints the
 * document the server emits — one row per required capability (decision,
 * mechanisms, justified exclusions, gap) followed by the whole trail it was
 * projected from — built from the two responses and nothing else. Printing is the
 * browser's; no PDF library here to disagree with the screen.
 */

import type {
  AuditEventRead,
  BaselineAuditLog,
  BaselineStatement,
  StatementMechanism,
  StatementRow,
  StatementZone,
} from '../../api/types'
import { ACTOR, AUDIT_EVENT, DISPOSITION, OUTCOME, TIER } from '../../lib/labels'

const STYLE = `
  @page { size: A4 landscape; margin: 12mm 10mm }
  body { font: 11px/1.5 'IBM Plex Sans', system-ui, sans-serif; color: #182230; margin: 0 }
  h1 { font-size: 17px; margin: 0 0 2px }
  h2 { font-size: 12px; margin: 18px 0 6px; text-transform: uppercase; letter-spacing: .1em; color: #61707f }
  h3 { font-size: 11px; margin: 14px 0 4px }
  .sub { color: #61707f; font-size: 11px; margin: 0 0 14px }
  .meta { display: grid; grid-template-columns: 150px 1fr; gap: 3px 12px; font-size: 10.5px }
  .meta dt { color: #8a93a1 }
  .meta dd { margin: 0 }
  .mono { font-family: 'IBM Plex Mono', ui-monospace, monospace }
  .why { color: #4a5563 }
  .small { font-size: 9.5px; color: #61707f }
  table { width: 100%; border-collapse: collapse; font-size: 9px; table-layout: fixed }
  th { text-align: left; border-bottom: 1px solid #182230; padding: 4px 6px 4px 0; font-size: 8.5px;
       text-transform: uppercase; letter-spacing: .06em; color: #61707f }
  td { border-bottom: 1px solid #eceae4; padding: 4px 6px 4px 0; vertical-align: top;
       word-wrap: break-word; overflow-wrap: anywhere }
  tr { break-inside: avoid }
  .none { color: #8a93a1; font-style: italic; font-size: 10.5px }
  ul.limits { margin: 4px 0 0; padding-left: 16px; font-size: 9.5px; color: #61707f }
  footer { margin-top: 20px; border-top: 1px solid #ddd9d0; padding-top: 8px; font-size: 9px; color: #8a93a1 }
  .break { break-before: page }
`

function esc(value: unknown): string {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

function table(head: string[], widths: number[], rows: string[][], empty: string): string {
  if (rows.length === 0) return `<p class="none">${esc(empty)}</p>`
  const columns = widths.map((width) => `<col style="width:${width}%">`).join('')
  const header = head.map((cell) => `<th>${esc(cell)}</th>`).join('')
  const body = rows
    .map((cells) => `<tr>${cells.map((cell) => `<td>${esc(cell)}</td>`).join('')}</tr>`)
    .join('')
  return `<table><colgroup>${columns}</colgroup><thead><tr>${header}</tr></thead><tbody>${body}</tbody></table>`
}

const control = (mechanism: StatementMechanism): string =>
  mechanism.framework && mechanism.official_id
    ? `${mechanism.framework} ${mechanism.official_id}`
    : mechanism.control_id

/** What went into the baseline, one line per mechanism, with how it got there. */
function included(row: StatementRow): string {
  const taken = row.mechanisms.filter((mechanism) => mechanism.included)
  if (taken.length === 0) return '—'
  return taken
    .map((mechanism) => {
      const adopted = mechanism.adopted ? ' [sugerencia adoptada]' : ''
      const despite = mechanism.despite_gating ? ` [pese a: ${mechanism.despite_gating}]` : ''
      return `${control(mechanism)} (${DISPOSITION[mechanism.disposition].label})${adopted}${despite}`
    })
    .join('\n')
}

/** The SoA's own deliverable: what was left out, under which rule, on which premise. */
function excluded(row: StatementRow): string {
  const out = row.mechanisms.filter((mechanism) =>
    ['not_applicable', 'wrong_scope', 'objective_without_mechanism'].includes(
      mechanism.disposition,
    ),
  )
  if (out.length === 0) return '—'
  return out
    .map(
      (mechanism) =>
        `${control(mechanism)} — ${DISPOSITION[mechanism.disposition].label}` +
        ` · ${mechanism.rule_id ?? 'sin regla'}` +
        (mechanism.evidence.length ? ` · ${mechanism.evidence.join(', ')}` : ''),
    )
    .join('\n')
}

function gapText(row: StatementRow): string {
  if (!row.gap) return '—'
  const residual =
    row.gap.residual === null ? '' : ` · residuo ${Math.round(row.gap.residual * 100)} %`
  return `${row.gap.kind}${residual}${row.gap_accepted ? ' · asumido por escrito' : ''}`
}

function statementRows(zone: StatementZone): string[][] {
  return zone.rows.map((row) => [
    `${row.capability_name}\n${row.capability_id}`,
    `${TIER[row.tier].label}${row.phase === null ? '' : ` · fase ${row.phase}`}`,
    OUTCOME[row.outcome].label + (row.in_signed_baseline ? '' : ' (fuera de la firma)'),
    included(row),
    excluded(row),
    row.jurisdictions.join(', ') || '—',
    gapText(row),
    row.human_rationale ?? row.engine_rationale,
    row.audit_sequences.join(', '),
  ])
}

function zoneSection(zone: StatementZone): string {
  const counts = zone.counts
  return `
<h3>Zona ${esc(zone.zone_id)}${zone.target_sl === null ? '' : ` · SL-objetivo ${esc(zone.target_sl)}`}</h3>
<p class="why small">${esc(zone.rationale)}</p>
${table(
  [
    'capacidad exigida',
    'tier / fase',
    'decisión',
    'controles incorporados',
    'exclusiones justificadas (regla · premisa)',
    'jurisdicción',
    'hueco',
    'justificación registrada',
    'bitácora',
  ],
  [13, 7, 8, 15, 18, 6, 8, 20, 5],
  statementRows(zone),
  'Ninguna capacidad declarada en esta zona.',
)}
<p class="small">
  ${esc(counts.capabilities)} capacidad(es) · ${esc(counts.signed)} dentro de lo firmado ·
  ${esc(counts.included_mechanisms)} control(es) incorporado(s) ·
  ${esc(counts.offered_not_taken)} ofrecido(s) y no tomado(s) ·
  ${esc(counts.justified_exclusions)} exclusión(es) justificada(s) ·
  ${esc(counts.organizational_deferrals)} desplazado(s) a la organización ·
  bloque obligatorio ${zone.tier_0_complete ? 'completo' : 'incompleto'}.
</p>`
}

function trailRows(events: AuditEventRead[]): string[][] {
  return events.map((event) => [
    String(event.sequence),
    new Date(event.recorded_at).toLocaleString('es-ES'),
    ACTOR[event.actor],
    AUDIT_EVENT[event.event_type] ?? event.event_type,
    event.decision,
    event.rationale,
  ])
}

function documentFor(statement: BaselineStatement, log: BaselineAuditLog): string {
  const versions = Object.entries(statement.versions)
    .map(([name, value]) => `${name} ${value}`)
    .join(' · ')
  const counts = statement.counts

  return `<!doctype html><html lang="es"><head><meta charset="utf-8">
<title>Declaración de aplicabilidad — ${esc(statement.profile_name)}</title>
<style>${STYLE}</style></head><body>
<h1>${esc(statement.profile_name)}</h1>
<p class="sub">Declaración de aplicabilidad de la línea base firmada ·
<span class="mono">${esc(statement.baseline_id)}</span></p>

<dl class="meta">
  <dt>Firmada por</dt><dd>${esc(statement.signed_by)}</dd>
  <dt>Fecha</dt><dd>${esc(new Date(statement.signed_at).toLocaleString('es-ES'))}</dd>
  <dt>Activo</dt><dd class="mono">${esc(statement.profile_id)}</dd>
  <dt>Zonas</dt><dd>${esc(statement.zones.map((zone) => zone.zone_id).join(' · ') || '—')}</dd>
  <dt>Bloque obligatorio</dt><dd>${statement.tier_0_complete ? 'completo' : 'incompleto'}</dd>
  <dt>Versiones que rigieron</dt><dd class="mono">${esc(versions || '—')}</dd>
  <dt>Ejecución del motor</dt><dd class="mono">${esc(statement.run_id)}</dd>
  <dt>Integridad del registro</dt><dd>${esc(log.chain.detail)}</dd>
</dl>

<h2>Qué es este documento</h2>
<p class="why">${esc(statement.rationale)}</p>
<ul class="limits">${statement.limitations
    .map((limitation) => `<li>${esc(limitation)}</li>`)
    .join('')}</ul>

<h2>Justificación de la firma</h2>
<p class="why">${esc(statement.signature_rationale)}</p>

<h2>Declaración por zona</h2>
${statement.zones.map(zoneSection).join('')}

<h2>Resumen</h2>
<p class="why small">
  ${esc(counts.capabilities)} capacidad(es) exigida(s) en ${esc(statement.zones.length)} zona(s):
  ${esc(counts.implemented)} cubierta(s), ${esc(counts.compensated)} compensada(s),
  ${esc(counts.deferred)} en la capa organizativa, ${esc(counts.accepted_gaps)} hueco(s) asumido(s)
  por escrito, ${esc(counts.open_gaps)} hueco(s) abierto(s) y ${esc(counts.roadmap)} en el plan por
  fases fuera de la firma.
</p>

<h2 class="break">Bitácora completa (append-only)</h2>
${table(
  ['#', 'cuándo', 'quién', 'qué', 'decisión', 'por qué'],
  [4, 10, 6, 14, 26, 40],
  trailRows(log.events),
  'Sin entradas.',
)}

<footer>
  ${esc(log.events.length)} entrada(s) · ${esc(log.engine_events)} del motor y ${esc(log.human_events)} del humano.
  ${esc(log.chain.detail)}
</footer>
</body></html>`
}

/**
 * Opens the document in its own window and asks the browser to print it. Returns
 * false when the window was blocked, so the caller can say so.
 */
export function printBaseline(statement: BaselineStatement, log: BaselineAuditLog): boolean {
  const target = window.open('', '_blank')
  if (!target) return false

  target.document.write(documentFor(statement, log))
  target.document.close()
  target.focus()
  // Let the document lay out before the print dialog measures it.
  target.setTimeout(() => target.print(), 250)
  return true
}
