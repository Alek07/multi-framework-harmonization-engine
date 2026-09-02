/**
 * Draft -> `AssetProfile`, the one piece of server logic this client mirrors.
 *
 * `POST /asset/parse` returns a *draft* with every uncertain value null, plus
 * the paths still missing. The operator then corrects it, and the corrected
 * profile is what the next call carries — there is deliberately no endpoint that
 * promotes a draft, because promoting one is a pure offline function and a sixth
 * endpoint would open a closed surface to buy nothing
 * (`server/app/parse/router.py`).
 *
 * The consequence is that the client has to run that function itself, so the
 * two below are a deliberate transcription of `server/app/parse/completion.py`
 * (`missing_required`, `to_profile`, `profile_id_for`) and of nothing else. They
 * check *presence*, never semantics: whether an SL of 3 is the right SL for a
 * zone is not a question this UI answers — the operator does, and the engine
 * reads what they wrote. If `completion.py` changes, this file changes with it.
 */

import {
  FR_FIELDS,
  NATURE_FIELDS,
  type AssetProfile,
  type AssetProfileDraft,
  type Conduit,
  type Criticality,
  type SLVector,
  type SLVectorDraft,
  type Zone,
  type ZoneDraft,
} from '../api/types'

const NON_ALNUM = /[^A-Z0-9]+/g

/** An id is a key, not an observation: derived, never asked of the model. */
export function profileIdFor(draft: AssetProfileDraft, explicit?: string | null): string {
  if (explicit) return explicit
  const folded = (draft.name ?? '')
    .normalize('NFKD')
    // Fold accents rather than replace them: this id is read back in the audit
    // log, and `ESTACI-N` would be nobody's asset.
    .replace(/[̀-ͯ]/g, '')
    .replace(/[^\x20-\x7E]/g, '')
  const slug = folded.toUpperCase().replace(NON_ALNUM, '-').replace(/^-+|-+$/g, '')
  return slug ? `ASSET-${slug}` : 'ASSET'
}

/**
 * A zone the operator adds by hand, with every premise undeclared.
 *
 * Nothing is guessed into it — least of all the five of `nature`, where a
 * fabricated `false` silently removes mechanisms from the baseline and a
 * fabricated `true` suppresses the exclusion an embedded controller is owed.
 */
export function emptyZone(id: string): ZoneDraft {
  return {
    id,
    target_sl: null,
    nature: {
      general_purpose_os: null,
      networked: null,
      hybrid_it_ot: null,
      interactive_users: null,
      office_it_surface: null,
    },
    purdue: null,
    role: null,
    position: null,
    sl_vector: null,
    safety_out_of_scope: null,
    reference: null,
    sectors: [],
  }
}

/** An SL vector is all seven FRs or none: a half vector is a gap, not a value. */
function missingSLVector(vector: SLVectorDraft, prefix: string): string[] {
  const present = FR_FIELDS.filter((fr) => vector[fr] != null)
  if (present.length === 0) return []
  return FR_FIELDS.filter((fr) => vector[fr] == null).map((fr) => `${prefix}.sl_vector.${fr}`)
}

function missingInZone(zone: ZoneDraft, index: number): string[] {
  const prefix = `zones[${zone.id || index}]`
  const missing = zone.target_sl == null ? [`${prefix}.target_sl`] : []
  // Asked once per zone: gating reads these premises from the zone, so a zone
  // left without them is a zone the core cannot gate (UCM-9).
  missing.push(
    ...NATURE_FIELDS.filter((field) => zone.nature?.[field] == null).map(
      (field) => `${prefix}.nature.${field}`,
    ),
  )
  return zone.sl_vector ? [...missing, ...missingSLVector(zone.sl_vector, prefix)] : missing
}

/**
 * Every value `AssetProfile` requires that the draft does not have, in document
 * order — the same list, computed the same way, that the server returned for the
 * model's own output. Recomputed here because the operator's corrections change
 * it, and a "complete" flag that stopped updating as they typed would be worse
 * than none.
 */
export function missingRequired(draft: AssetProfileDraft): string[] {
  const missing: string[] = []

  if (!draft.name) missing.push('name')
  if (draft.case == null) missing.push('case')

  if (draft.zones.length === 0) missing.push('zones')
  draft.zones.forEach((zone, index) => missing.push(...missingInZone(zone, index)))

  draft.conduits.forEach((conduit, index) => {
    const prefix = `conduits[${conduit.id || index}]`
    if (conduit.endpoints.length === 0) missing.push(`${prefix}.endpoints`)
    if (!conduit.control) missing.push(`${prefix}.control`)
  })

  missing.push(
    ...(['physical_consequence', 'scale', 'threat_model'] as const)
      .filter((field) => draft.criticality[field] == null)
      .map((field) => `criticality.${field}`),
  )

  return missing
}

function zoneOf(draft: ZoneDraft): Zone {
  const vector = draft.sl_vector
  const complete =
    vector != null && FR_FIELDS.every((fr) => vector[fr] != null)
      ? (Object.fromEntries(FR_FIELDS.map((fr) => [fr, vector[fr] as number])) as SLVector)
      : null

  return {
    id: draft.id,
    target_sl: draft.target_sl as number,
    nature: {
      general_purpose_os: draft.nature.general_purpose_os as boolean,
      networked: draft.nature.networked as boolean,
      hybrid_it_ot: draft.nature.hybrid_it_ot as boolean,
      interactive_users: draft.nature.interactive_users as boolean,
      office_it_surface: draft.nature.office_it_surface as boolean,
    },
    ...(draft.purdue ? { purdue: draft.purdue } : {}),
    ...(draft.role ? { role: draft.role } : {}),
    ...(draft.position ? { position: draft.position } : {}),
    ...(complete ? { sl_vector: complete } : {}),
    safety_out_of_scope: draft.safety_out_of_scope ?? false,
    ...(draft.reference ? { reference: draft.reference } : {}),
    // Carried whole, empty list and all: a zone that narrows nothing inherits the
    // asset's sectors, and dropping the field is what lost the scope (UCM-57).
    sectors: draft.sectors,
  }
}

/**
 * The `AssetProfile` the core runs on, or null while anything is still missing.
 *
 * There is no partial promotion and no default value, for the same reason the
 * server refuses one: a profile with an invented SL would run through the core
 * and produce a baseline nobody decided.
 */
export function toProfile(
  draft: AssetProfileDraft,
  profileId?: string | null,
): AssetProfile | null {
  if (missingRequired(draft).length > 0) return null

  const conduits: Conduit[] = draft.conduits.map((conduit) => ({
    id: conduit.id,
    endpoints: conduit.endpoints,
    control: conduit.control as string,
  }))

  const criticality: Criticality = {
    physical_consequence: draft.criticality.physical_consequence as string,
    scale: draft.criticality.scale!,
    threat_model: draft.criticality.threat_model as string,
    ...(draft.criticality.consequence_path
      ? { consequence_path: draft.criticality.consequence_path }
      : {}),
    ...(draft.criticality.attack_reference
      ? { attack_reference: draft.criticality.attack_reference }
      : {}),
  }

  return {
    id: profileIdFor(draft, profileId),
    name: draft.name as string,
    case: draft.case!,
    sectors: draft.sectors,
    zones: draft.zones.map(zoneOf),
    conduits,
    criticality,
  }
}

/** Deep copy of a draft, so a correction never mutates what the model returned. */
export function cloneDraft(draft: AssetProfileDraft): AssetProfileDraft {
  return structuredClone(draft)
}
