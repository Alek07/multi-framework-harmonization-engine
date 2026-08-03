/**
 * The shape of a composition session: what the provider offers, and the few
 * helpers that read the engine's answers.
 *
 * The division of labour this module encodes is the whole point. The engine owns
 * every fact — which options exist, what they cover, which mandates are open,
 * which conflicts it refuses to settle, which mechanisms gating removed — and
 * all of it arrives in `CandidatesResponse` and is read from there, never
 * recomputed. What the provider holds is what the operator has *done*.
 */

import { createContext, useContext } from 'react'

import type {
  AssetProfile,
  AssetProfileDraft,
  BaselineAuditLog,
  CandidatesResponse,
  CapabilityCandidates,
  CapabilityGap,
  ComposedBaseline,
  CompositionChoice,
  ConsequenceScale,
  FoundationalRequirement,
  Jurisdiction,
  NatureField,
  ParseResult,
  RegionalDelta,
  Signature,
  ZoneCandidates,
} from '../api/types'

export type Step = 1 | 2 | 3 | 4 | 5
export type ProfileSource = 'parse' | 'frozen'

/** Profiles frozen in the repository (UCM-1/UCM-2), addressable by id. */
export const FROZEN_PROFILES = [
  { id: 'PROFILE-A', label: 'PROFILE-A — corredor SCADA/PLC (OT puro)' },
  { id: 'PROFILE-B', label: 'PROFILE-B — activo híbrido IT/OT' },
] as const

/** The two cumulative readings of UCM-17. The order asks a different question. */
export const DELTA_ORDERS: { label: string; regions: Jurisdiction[] }[] = [
  { label: 'US → +EU', regions: ['US', 'EU'] },
  { label: 'EU → +US', regions: ['EU', 'US'] },
]

/** One field the operator changed, and what the model had proposed. */
export interface Correction {
  path: string
  from: string
  to: string
}

export interface Blocker {
  text: string
  zoneId: string
  capabilityId: string
}

export interface ZoneProgress {
  tier0Done: number
  tier0Total: number
  gaps: number
  gapsAcknowledged: number
  conflictsOpen: number
}

export interface Progress extends ZoneProgress {
  blockers: Blocker[]
  byZone: Record<string, ZoneProgress>
}

export function emptyZoneProgress(): ZoneProgress {
  return { tier0Done: 0, tier0Total: 0, gaps: 0, gapsAcknowledged: 0, conflictsOpen: 0 }
}

export function keyOf(zoneId: string, capabilityId: string): string {
  return `${zoneId}|${capabilityId}`
}

export interface CompositionApi {
  // --- session ---------------------------------------------------------------
  backendUp: boolean | null
  step: Step
  goToStep: (step: Step) => void
  zoneId: string | null
  setZoneId: (zoneId: string) => void
  focusRequest: string | null
  focusOn: (domId: string, zoneId: string, step: Step) => void
  clearFocus: () => void

  // --- stage 1: the asset ----------------------------------------------------
  source: ProfileSource
  description: string
  setDescription: (value: string) => void
  descriptionLocked: boolean
  unlockDescription: () => void
  parsing: boolean
  parseError: string | null
  parseResult: ParseResult | null
  draft: AssetProfileDraft | null
  corrections: Correction[]
  missing: string[]
  profile: AssetProfile | null
  frozenProfileId: string | null
  runParse: () => Promise<void>
  selectFrozenProfile: (profileId: string) => void
  correctTargetSL: (zoneIndex: number, value: number) => void
  correctSL: (zoneIndex: number, requirement: FoundationalRequirement) => void
  correctNature: (field: NatureField) => void
  correctCriticality: (scale: ConsequenceScale) => void

  // --- stage 2: the candidates ----------------------------------------------
  candidates: CandidatesResponse | null
  candidatesLoading: boolean
  candidatesError: string | null
  loadCandidates: () => Promise<void>
  explaining: string | null
  explainCapability: (zoneId: string, capabilityId: string) => Promise<void>

  // --- the human's decisions -------------------------------------------------
  selectionsFor: (zoneId: string, capabilityId: string) => string[]
  toggleSelection: (zoneId: string, capabilityId: string, controlId: string) => void
  reasonFor: (zoneId: string, capabilityId: string) => string
  setReason: (zoneId: string, capabilityId: string, value: string) => void
  gapAccepted: (zoneId: string, capabilityId: string) => boolean
  toggleGap: (zoneId: string, capabilityId: string) => void
  choices: CompositionChoice[]
  progress: Progress

  // --- stage 3: the regional delta -------------------------------------------
  delta: RegionalDelta | null
  deltaLoading: boolean
  deltaError: string | null
  deltaOrder: number
  setDeltaOrder: (index: number) => void
  loadDelta: () => Promise<void>

  // --- stages 4 and 5: signature and trail -----------------------------------
  signing: boolean
  signError: string | null
  baseline: ComposedBaseline | null
  auditLog: BaselineAuditLog | null
  auditLogError: string | null
  signed: boolean
  /** True when the baseline was signed; false leaves `signError` on screen. */
  sign: (signature: Signature) => Promise<boolean>
}

export const CompositionContext = createContext<CompositionApi | null>(null)

export function useComposition(): CompositionApi {
  const value = useContext(CompositionContext)
  if (!value) throw new Error('useComposition fuera de <CompositionProvider>')
  return value
}

/** The zone the operator is composing in, as the engine described it. */
export function useActiveZone(): ZoneCandidates | undefined {
  const { candidates, zoneId } = useComposition()
  if (!candidates || !zoneId) return undefined
  return candidates.zones.find((zone) => zone.zone.zone_id === zoneId)
}

/**
 * The gap the engine declared for one capability, wherever it declared it.
 *
 * Four layers can declare one — resolution, gating, prioritisation, retrieval —
 * and a capability with no candidate must carry one from at least one of them
 * or the response would not have been constructible (invariant 2).
 */
export function declaredGap(capability: CapabilityCandidates): CapabilityGap | null {
  return (
    capability.resolution.gap ??
    capability.gating.gap ??
    capability.priority.gap ??
    capability.retrieval?.gap ??
    null
  )
}
