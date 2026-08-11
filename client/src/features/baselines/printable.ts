/**
 * The signed baseline as a printable document, with its whole trail in it.
 *
 * Built from the two things the server returned and nothing else, so the paper
 * says exactly what the ledger says. Printing is the browser's; there is no PDF
 * library here to disagree with the screen.
 */

import type { AuditEventRead, BaselineAuditLog, BaselineSummary } from '../../api/types'
import { ACTOR, AUDIT_EVENT } from '../../lib/labels'
import { decisionsOf, type DecisionRow } from './trail'

const STYLE = `
  @page { size: A4; margin: 16mm 14mm }
  body { font: 11px/1.5 'IBM Plex Sans', system-ui, sans-serif; color: #182230; margin: 0 }
  h1 { font-size: 17px; margin: 0 0 2px }
  h2 { font-size: 12px; margin: 20px 0 6px; text-transform: uppercase; letter-spacing: .1em; color: #61707f }
  .sub { color: #61707f; font-size: 11px; margin: 0 0 14px }
  .meta { display: grid; grid-template-columns: 150px 1fr; gap: 3px 12px; font-size: 10.5px }
  .meta dt { color: #8a93a1 }
  .meta dd { margin: 0 }
  .mono { font-family: 'IBM Plex Mono', ui-monospace, monospace }
  .why { color: #4a5563 }
  table { width: 100%; border-collapse: collapse; font-size: 9.5px; table-layout: fixed }
  th { text-align: left; border-bottom: 1px solid #182230; padding: 4px 6px 4px 0; font-size: 9px;
       text-transform: uppercase; letter-spacing: .06em; color: #61707f }
  td { border-bottom: 1px solid #eceae4; padding: 4px 6px 4px 0; vertical-align: top;
       word-wrap: break-word; overflow-wrap: anywhere }
  tr { break-inside: avoid }
  .none { color: #8a93a1; font-style: italic; font-size: 10.5px }
  footer { margin-top: 22px; border-top: 1px solid #ddd9d0; padding-top: 8px; font-size: 9px; color: #8a93a1 }
`

function esc(value: unknown): string {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

function table(head: string[], rows: string[][], empty: string): string {
  if (rows.length === 0) return `<p class="none">${esc(empty)}</p>`
  const columns = head.map(() => `<col style="width:${(100 / head.length).toFixed(1)}%">`).join('')
  const header = head.map((cell) => `<th>${esc(cell)}</th>`).join('')
  const body = rows
    .map((cells) => `<tr>${cells.map((cell) => `<td>${esc(cell)}</td>`).join('')}</tr>`)
    .join('')
  return `<table><colgroup>${columns}</colgroup><thead><tr>${header}</tr></thead><tbody>${body}</tbody></table>`
}

const decisionRows = (rows: DecisionRow[]): string[][] =>
  rows.map((row) => [row.zoneId, row.capabilityId, row.controlId, row.rationale])

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

function documentFor(baseline: BaselineSummary, log: BaselineAuditLog): string {
  const decisions = decisionsOf(log)
  const versions = Object.entries(baseline.versions)
    .map(([name, value]) => `${name} ${value}`)
    .join(' · ')
  const mandates = Object.entries(baseline.closed_mandates)
    .map(([zone, ids]) => `${zone}: ${ids.join(', ')}`)
    .join(' — ')

  return `<!doctype html><html lang="es"><head><meta charset="utf-8">
<title>Línea base ${esc(baseline.baseline_id)}</title><style>${STYLE}</style></head><body>
<h1>${esc(baseline.profile_name)}</h1>
<p class="sub">Línea base firmada · <span class="mono">${esc(baseline.baseline_id)}</span></p>

<dl class="meta">
  <dt>Firmada por</dt><dd>${esc(baseline.signed_by)}</dd>
  <dt>Fecha</dt><dd>${esc(new Date(baseline.signed_at).toLocaleString('es-ES'))}</dd>
  <dt>Activo</dt><dd class="mono">${esc(baseline.profile_id)}</dd>
  <dt>Zonas</dt><dd>${esc(baseline.zone_ids.join(' · ') || '—')}</dd>
  <dt>Bloque obligatorio</dt><dd>${baseline.tier_0_complete ? 'completo' : 'incompleto'}</dd>
  <dt>Versiones</dt><dd class="mono">${esc(versions || '—')}</dd>
  <dt>Ejecución del motor</dt><dd class="mono">${esc(baseline.run_id)}</dd>
  <dt>Integridad del registro</dt><dd>${esc(log.chain.detail)}</dd>
</dl>

<h2>Justificación de la firma</h2>
<p class="why">${esc(baseline.signature_rationale)}</p>

${mandates ? `<h2>Mandatos que cerró el humano</h2><p class="why">${esc(mandates)}</p>` : ''}

<h2>Elecciones por capacidad</h2>
${table(
  ['zona', 'capacidad', 'control', 'razón escrita'],
  decisionRows(decisions.selected),
  'No se seleccionó ningún mecanismo: todo el bloque obligatorio quedó ratificado o aceptado como hueco.',
)}
${
  decisions.ratified > 0
    ? `<p class="none">Además, ${decisions.ratified} mandato(s) retenido(s) por el motor y ratificado(s) al firmar — no son una elección entre equivalentes.</p>`
    : ''
}

<h2>Huecos que viajan a la línea base</h2>
${table(
  ['zona', 'capacidad', 'control', 'razón escrita'],
  decisionRows(decisions.gaps),
  'Ninguno: no se aceptó ningún hueco.',
)}

<h2>Conflictos resueltos por el humano</h2>
${table(
  ['zona', 'capacidad', 'control descartado', 'razón escrita'],
  decisionRows(decisions.rejected),
  'Ninguno: no hubo contradicciones que resolver.',
)}

<h2>Bitácora completa (append-only)</h2>
${table(
  ['#', 'cuándo', 'quién', 'qué', 'decisión', 'por qué'],
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
 * Opens the document in its own window and asks the browser to print it.
 *
 * Returns false when the window was blocked, so the caller can say so rather
 * than leave a button that appears to do nothing.
 */
export function printBaseline(baseline: BaselineSummary, log: BaselineAuditLog): boolean {
  const target = window.open('', '_blank')
  if (!target) return false

  target.document.write(documentFor(baseline, log))
  target.document.close()
  target.focus()
  // Let the document lay out before the print dialog measures it.
  target.setTimeout(() => target.print(), 250)
  return true
}
