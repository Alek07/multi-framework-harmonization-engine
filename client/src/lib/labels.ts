/**
 * How the engine's vocabulary is written on screen.
 *
 * Presentational only, and that is a boundary rather than a style note: nothing
 * here reorders, scores or hides anything. The identifiers stay the server's
 * (`not_applicable`, `tier_0`) — they are what the audit log records and what
 * the memoir cites — and these are the Spanish words the operator reads next to
 * them (language rule, CLAUDE.md §8).
 */

import type {
  CapabilityStatus,
  ConflictType,
  ConsequenceScale,
  Framework,
  GapKind,
  GatingOutcome,
  Jurisdiction,
  MappingType,
  NatureField,
  OrdinalLevel,
  PriorityTier,
  ResolutionMethod,
  RetrievalStatus,
  ZoneDomain,
} from '../api/types'

interface Chip {
  label: string
  className: string
}

/** The five frameworks of the catalog, each with the design's own chip colour. */
export const FRAMEWORK: Record<Framework, Chip> = {
  IEC62443: { label: 'IEC 62443', className: 'bg-[#e4ecfa] text-[#1d4c9e]' },
  CSF: { label: 'CSF 2.0', className: 'bg-[#ece6f8] text-[#5b3ea8]' },
  CIS: { label: 'CIS v8', className: 'bg-[#e2f2ea] text-[#1d6f4c]' },
  NIS2: { label: 'NIS2', className: 'bg-[#fdeee2] text-[#a35415]' },
  IMO: { label: 'IMO', className: 'bg-[#e3f1f5] text-[#186a80]' },
}

/** Glyph + word for a mapping type. The order they are listed in is the core's. */
export const MAPPING_TYPE: Record<MappingType, { glyph: string; label: string }> = {
  total: { glyph: '●', label: 'total' },
  partial: { glyph: '◐', label: 'partial' },
  compensatory: { glyph: '▲', label: 'compensatory' },
  contextual: { glyph: '◇', label: 'contextual' },
}

export const JURISDICTION: Record<Jurisdiction, string> = {
  US: 'US',
  EU: 'EU',
  INTL: 'INTL',
  'INTL-MARITIME': 'INTL-MARITIME',
}

export const ZONE_DOMAIN: Record<ZoneDomain, string> = {
  OT: 'OT',
  IT: 'IT',
  HYBRID: 'IT/OT',
}

/** The three — and only three — ways a mechanism leaves a zone's baseline. */
export const GATING_OUTCOME: Record<GatingOutcome, Chip> = {
  not_applicable: {
    label: 'no-aplica',
    className: 'bg-[#eef0f2] text-ink-2',
  },
  wrong_scope: {
    label: 'ámbito-equivocado',
    className: 'bg-defer-tint text-defer',
  },
  objective_without_mechanism: {
    label: 'objetivo-sin-mecanismo',
    className: 'bg-alert-tint text-alert-ink',
  },
}

export const CAPABILITY_STATUS: Record<CapabilityStatus, string> = {
  covered_by_mechanism: 'cubierta por mecanismo',
  compensatory_required: 'requiere control compensatorio',
  deferred_to_organizational_layer: 'diferida a la capa organizativa',
}

export const GAP_KIND: Record<GapKind, string> = {
  no_candidate: 'sin candidato',
  no_effective_mechanism: 'objetivo-sin-mecanismo',
  partial_only: 'solo cobertura parcial',
  residual_coverage: 'cobertura residual',
}

export const CONFLICT_TYPE: Record<ConflictType, string> = {
  overlap: 'solape de alcance',
  granularity: 'granularidad 1:N',
  contradiction: 'contradicción real',
}

export const RESOLUTION_METHOD: Record<ResolutionMethod, string> = {
  collapsed: 'colapso por capacidad',
  coverage_weights: 'pesos de cobertura',
  framework_precedence: 'precedencia de marco',
  safety_override: 'override de seguridad (OT)',
}

export const TIER: Record<PriorityTier, string> = {
  tier_0: 'T0',
  tier_1: 'T1',
}

export const ORDINAL: Record<OrdinalLevel, string> = {
  low: 'baja',
  medium: 'media',
  high: 'alta',
}

export const CONSEQUENCE_SCALE: Record<ConsequenceScale, string> = {
  catastrophic: 'catastrófica',
  high: 'alta',
  moderate: 'moderada',
  low: 'baja',
}

export const NATURE: Record<NatureField, string> = {
  general_purpose_os: 'SO de propósito general',
  networked: 'en red',
  hybrid_it_ot: 'híbrido IT/OT',
  interactive_users: 'usuarios interactivos',
  office_it_surface: 'superficie IT de oficina',
}

export const RETRIEVAL_STATUS: Record<RetrievalStatus, string> = {
  ok: 'recuperación activa',
  disabled: 'recuperación desactivada',
  unavailable: 'recuperación no disponible',
}

/** `official_crosswalk` draws a solid border, `author_judgment` a dotted one. */
export function provenanceLabel(source: string): string {
  return source
}

export function coverageText(coverage: number): string {
  return coverage.toFixed(2)
}
