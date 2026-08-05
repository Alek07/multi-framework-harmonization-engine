/**
 * How the engine's vocabulary is written on screen.
 *
 * Presentational only, and that is a boundary rather than a style note: nothing
 * here reorders, scores or hides anything. The identifiers stay the server's
 * (`not_applicable`, `tier_0`) — they are what the audit log records and what
 * the memoir cites — and these are the Spanish words the operator reads instead
 * of them (language rule, CLAUDE.md §8).
 *
 * The rule this module enforces on the whole client: **an operator never reads a
 * raw identifier, an endpoint route or an internal rule name.** Where the raw
 * value still matters for traceability it goes in a `title` tooltip, never in
 * the visible label.
 */

import type {
  AuditActor,
  AuditEventType,
  CandidateStatus,
  CapabilityStatus,
  CaseType,
  ConflictType,
  ConsequenceScale,
  FoundationalRequirement,
  Framework,
  GapKind,
  GatingOutcome,
  Jurisdiction,
  MappingType,
  NatureField,
  OrdinalLevel,
  PriorityTier,
  ProvenanceSource,
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

/** Which standard each framework chip stands for, for the legend and tooltips. */
export const FRAMEWORK_NOTE: Record<Framework, string> = {
  IEC62443: 'Norma industrial de ciberseguridad para sistemas de control (OT).',
  CSF: 'Marco de ciberseguridad del NIST, de uso general.',
  CIS: 'Controles CIS v8, prácticas concretas de TI.',
  NIS2: 'Directiva europea: obligación legal, no práctica recomendada.',
  IMO: 'Resolución marítima de la OMI para la gestión del riesgo cibernético a bordo.',
}

/**
 * How much of a capability an option covers, in words rather than in the
 * catalog's term. The glyph is kept because the legend explains it once.
 */
export const MAPPING_TYPE: Record<MappingType, { glyph: string; label: string; note: string }> = {
  total: {
    glyph: '●',
    label: 'cubre el requisito entero',
    note: 'Este control resuelve la capacidad por sí solo.',
  },
  partial: {
    glyph: '◐',
    label: 'cubre una parte',
    note: 'Hace falta combinarlo con otro control para cerrar la capacidad.',
  },
  compensatory: {
    glyph: '▲',
    label: 'alternativa compensatoria',
    note: 'No hace lo mismo, pero cubre el objetivo por otra vía cuando no hay mecanismo directo.',
  },
  contextual: {
    glyph: '◇',
    label: 'aplica solo en cierto contexto',
    note: 'Solo cuenta si se dan las condiciones que describe.',
  },
}

/** Where a proposed equivalence comes from — the two ways, in plain words. */
export const PROVENANCE: Record<ProvenanceSource, { label: string; note: string }> = {
  official_crosswalk: {
    label: 'equivalencia oficial',
    note: 'La equivalencia entre marcos está publicada por el propio organismo.',
  },
  author_judgment: {
    label: 'equivalencia propuesta',
    note: 'La equivalencia la propone este catálogo; ningún organismo la ha publicado. Revísala.',
  },
}

export const JURISDICTION: Record<Jurisdiction, string> = {
  US: 'EE. UU.',
  EU: 'Unión Europea',
  INTL: 'Internacional',
  'INTL-MARITIME': 'Internacional marítimo',
}

/** Short form for chips where the long name does not fit. */
export const JURISDICTION_SHORT: Record<Jurisdiction, string> = {
  US: 'EE. UU.',
  EU: 'UE',
  INTL: 'Intl.',
  'INTL-MARITIME': 'Intl. marítimo',
}

export const ZONE_DOMAIN: Record<ZoneDomain, string> = {
  OT: 'Zona industrial (OT)',
  IT: 'Zona ofimática (IT)',
  HYBRID: 'Zona mixta (IT/OT)',
}

export const CASE_TYPE: Record<CaseType, { label: string; note: string }> = {
  PURE_OT: {
    label: 'Solo industrial (OT)',
    note: 'El activo es puramente de control industrial: no hay superficie ofimática dentro de él.',
  },
  HYBRID_IT_OT: {
    label: 'Mixto IT / OT',
    note: 'El activo mezcla control industrial y sistemas de propósito general en el mismo perímetro.',
  },
}

/** The seven families of requirements of la norma industrial, by their meaning. */
export const FR_MEANING: Record<FoundationalRequirement, string> = {
  FR1: 'Identificación y autenticación',
  FR2: 'Control de uso y permisos',
  FR3: 'Integridad del sistema',
  FR4: 'Confidencialidad de los datos',
  FR5: 'Segmentación y flujo de datos',
  FR6: 'Detección y respuesta a eventos',
  FR7: 'Disponibilidad de recursos',
}

/** The three — and only three — ways a control leaves a zone's baseline. */
export const GATING_OUTCOME: Record<GatingOutcome, Chip & { note: string }> = {
  not_applicable: {
    label: 'no aplica a este activo',
    className: 'bg-[#eef0f2] text-ink-2',
    note: 'El activo no tiene aquello que el control protege. Es una exclusión justificada, no una carencia.',
  },
  wrong_scope: {
    label: 'corresponde a la organización',
    className: 'bg-defer-tint text-defer',
    note: 'El control no se implanta en el activo, sino en políticas y procesos de la organización.',
  },
  objective_without_mechanism: {
    label: 'sin mecanismo técnico posible',
    className: 'bg-alert-tint text-alert-ink',
    note: 'El objetivo sigue siendo obligatorio, pero este activo no admite el mecanismo: hay que compensarlo.',
  },
}

export const CAPABILITY_STATUS: Record<CapabilityStatus, string> = {
  covered_by_mechanism: 'se cubre con un control del activo',
  compensatory_required: 'necesita una medida compensatoria',
  deferred_to_organizational_layer: 'se cubre en la capa organizativa',
}

export const GAP_KIND: Record<GapKind, { label: string; note: string }> = {
  no_candidate: {
    label: 'ningún control disponible',
    note: 'El catálogo no ofrece hoy ningún control para este requisito en esta zona.',
  },
  no_effective_mechanism: {
    label: 'sin mecanismo aplicable al activo',
    note: 'Hay controles, pero ninguno se puede implantar en este activo tal y como es.',
  },
  partial_only: {
    label: 'solo se cubre parcialmente',
    note: 'Los controles disponibles cubren una parte del requisito; el resto queda descubierto.',
  },
  residual_coverage: {
    label: 'queda cobertura residual',
    note: 'Se cubre casi todo, pero una fracción del requisito sigue sin controles.',
  },
}

export const CONFLICT_TYPE: Record<ConflictType, { label: string; note: string }> = {
  overlap: {
    label: 'controles que se solapan',
    note: 'Varios marcos piden lo mismo con distintas palabras.',
  },
  granularity: {
    label: 'un requisito repartido en varios controles',
    note: 'Un marco lo pide en un control y otro lo reparte en varios.',
  },
  contradiction: {
    label: 'exigencias incompatibles',
    note: 'Dos marcos piden cosas que no se pueden cumplir a la vez en esta zona.',
  },
}

export const RESOLUTION_METHOD: Record<ResolutionMethod, string> = {
  collapsed: 'se han unificado en un solo requisito',
  coverage_weights: 'se ha calculado cuánto cubre cada uno',
  framework_precedence: 'ha prevalecido el marco propio de esta zona',
  safety_override: 'ha prevalecido la seguridad física de la planta',
}

/** Tier 0 is not a rank: it is the block that has to be complete. */
export const TIER: Record<PriorityTier, { label: string; short: string; note: string }> = {
  tier_0: {
    label: 'Obligatorio',
    short: 'Oblig.',
    note: 'Exigido por el nivel de seguridad objetivo de la zona o por obligación legal. No se prioriza: se completa.',
  },
  tier_1: {
    label: 'Discrecional',
    short: 'Discr.',
    note: 'No es exigible: se prioriza según cuánto aporta, de qué depende y cuánto cuesta.',
  },
}

export const CANDIDATE_STATUS: Record<CandidateStatus, { label: string; note: string }> = {
  eligible: { label: 'disponible', note: 'Puedes elegirlo sin más.' },
  superseded: {
    label: 'apartado por una regla',
    note: 'Otra opción lo cubre mejor según las reglas. Sigue disponible: elegirlo exige justificarlo.',
  },
  contested: {
    label: 'en disputa',
    note: 'Entra en un conflicto que tienes que resolver tú.',
  },
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

export const NATURE: Record<NatureField, { label: string; note: string }> = {
  general_purpose_os: {
    label: 'Sistema operativo de propósito general',
    note: '¿Corre Windows, Linux o similar, en lugar de firmware cerrado?',
  },
  networked: {
    label: 'Conectado en red',
    note: '¿Está conectado a alguna red, aunque sea interna y aislada?',
  },
  hybrid_it_ot: {
    label: 'Mezcla mundo industrial y ofimático',
    note: '¿Conviven en él control industrial y sistemas de oficina?',
  },
  interactive_users: {
    label: 'Personas que inician sesión',
    note: '¿Hay usuarios que entran e interactúan con él, no solo procesos automáticos?',
  },
  office_it_surface: {
    label: 'Superficie ofimática (correo, navegación, ofimática)',
    note: '¿Expone herramientas de oficina que se puedan usar como vía de entrada?',
  },
}

export const RETRIEVAL_STATUS: Record<RetrievalStatus, string> = {
  ok: 'búsqueda de controles similares activa',
  disabled: 'búsqueda de controles similares desactivada',
  unavailable: 'búsqueda de controles similares no disponible',
}

/** Who wrote an entry in the record. */
export const ACTOR: Record<AuditActor, string> = {
  engine: 'sistema',
  human: 'persona',
}

/**
 * What each recorded event says, in the operator's words.
 *
 * The raw identifier is still what the ledger stores and what the memoir cites;
 * the screen shows it in the row's tooltip and this sentence in the cell.
 */
export const AUDIT_EVENT: Record<AuditEventType, string> = {
  run_started: 'inicio del análisis',
  zone_derived: 'zona identificada',
  capability_mapped: 'requisito asociado a controles',
  conflict_resolved: 'conflicto resuelto por regla',
  conflict_escalated: 'conflicto elevado a decisión humana',
  gap_declared: 'requisito sin cobertura declarado',
  mechanism_excluded: 'control excluido con justificación',
  capability_status_set: 'situación del requisito fijada',
  mandate_recorded: 'obligación registrada',
  mandate_outstanding: 'obligación pendiente de decisión',
  priority_assigned: 'prioridad asignada',
  roadmap_phased: 'plan por fases generado',
  stage_completed: 'etapa de cálculo completada',
  run_completed: 'análisis completado',
  candidates_retrieved: 'controles similares propuestos',
  candidate_set_aside: 'control apartado por el filtro declarado',
  option_selected: 'control elegido por la persona',
  option_rejected: 'control descartado por la persona',
  compensatory_declared: 'medida compensatoria declarada',
  gap_accepted: 'falta de cobertura aceptada',
  mechanism_ratified: 'control del sistema ratificado',
  baseline_signed: 'línea base firmada',
}

/** The four kinds of decision the record files, as the signature dialog lists them. */
export const CHOICE_KIND: Record<string, string> = {
  option_selected: 'Controles elegidos',
  compensatory_declared: 'Medidas compensatorias declaradas',
  option_rejected: 'Controles descartados al resolver conflictos',
  gap_accepted: 'Faltas de cobertura aceptadas',
}

const FIELD_WORDS: Record<string, string> = {
  name: 'nombre del activo',
  case: 'tipo de activo (solo OT o mixto IT/OT)',
  zones: 'al menos una zona',
  target_sl: 'nivel de seguridad objetivo',
  endpoints: 'extremos que conecta',
  control: 'control que protege el enlace',
  physical_consequence: 'qué pasa físicamente si falla',
  scale: 'gravedad de esa consecuencia',
  threat_model: 'modelo de amenaza de referencia',
}

/**
 * A path the completion check returns (`zones[Z-1].sl_vector.FR3`) written as
 * the sentence the operator needs in order to know what to fill in.
 */
export function fieldLabel(path: string): string {
  const zone = /^zones\[(.+?)\]\.(.+)$/.exec(path)
  if (zone) {
    const [, id, rest] = zone
    const fr = /^sl_vector\.(FR\d)$/.exec(rest)
    if (fr) return `zona ${id} · nivel exigido en ${fr[1]} (${FR_MEANING[fr[1] as FoundationalRequirement]})`
    // The five premises are the zone's own (UCM-9), so the label names the zone:
    // "sistema operativo corriente" on its own would be unreadable on a hybrid
    // asset, where the next zone answers it the other way.
    const nature = /^nature\.(.+)$/.exec(rest)
    if (nature) return `zona ${id} · ${NATURE[nature[1] as NatureField]?.label ?? nature[1]}`
    return `zona ${id} · ${FIELD_WORDS[rest] ?? rest}`
  }

  const conduit = /^conduits\[(.+?)\]\.(.+)$/.exec(path)
  if (conduit) return `enlace ${conduit[1]} · ${FIELD_WORDS[conduit[2]] ?? conduit[2]}`

  const criticality = /^criticality\.(.+)$/.exec(path)
  if (criticality) return `criticidad · ${FIELD_WORDS[criticality[1]] ?? criticality[1]}`

  return FIELD_WORDS[path] ?? path
}

export function coverageText(coverage: number): string {
  return `${Math.round(coverage * 100)} %`
}
