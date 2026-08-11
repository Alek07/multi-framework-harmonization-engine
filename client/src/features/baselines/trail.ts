/**
 * What a signed baseline's trail says the human decided.
 *
 * The trail carries the engine's run too; only the operator's own entries are
 * read here, and each keeps the sentence the ledger recorded for it.
 */

import type { AuditEventRead, BaselineAuditLog } from '../../api/types'

export interface DecisionRow {
  zoneId: string
  capabilityId: string
  controlId: string
  rationale: string
}

export interface Decisions {
  /** Mechanisms the operator picked, and compensatory controls they declared. */
  selected: DecisionRow[]
  /** Gaps that travel into the baseline with a written acceptance. */
  gaps: DecisionRow[]
  /** Contradictions the operator settled: what was discarded, and why. */
  rejected: DecisionRow[]
  /** Retained by the core and accepted by the signature — not chosen. */
  ratified: number
}

function row(event: AuditEventRead): DecisionRow {
  return {
    zoneId: event.zone_id ?? '—',
    capabilityId: event.capability_id ?? '—',
    controlId: event.control_id ?? '—',
    rationale: event.rationale,
  }
}

export function decisionsOf(log: BaselineAuditLog): Decisions {
  const mine = log.events.filter(
    (event) => event.actor === 'human' && event.baseline_id === log.baseline_id,
  )
  const of = (...types: AuditEventRead['event_type'][]) =>
    mine.filter((event) => types.includes(event.event_type)).map(row)

  return {
    selected: of('option_selected', 'compensatory_declared'),
    gaps: of('gap_accepted'),
    rejected: of('option_rejected'),
    ratified: mine.filter((event) => event.event_type === 'mechanism_ratified').length,
  }
}
