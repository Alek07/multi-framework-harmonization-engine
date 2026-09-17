/**
 * The composition session contract, and the helpers that read the engine's
 * answers. The engine owns every fact (options, coverage, open mandates,
 * conflicts, gated mechanisms) via `CandidatesResponse`, read never recomputed;
 * the provider holds only what the operator has *done*.
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
  DeltaMode,
  DeltaRegime,
  FoundationalRequirement,
  Jurisdiction,
  NatureField,
  ParseResult,
  RegionalDelta,
  Signature,
  ZoneCandidates,
} from '../../api/types'

export type Step = 1 | 2 | 3 | 4 | 5

/**
 * Why each step is not reachable yet, or `null` when it is. The lock says *what
 * is missing* rather than merely refusing, so the same sentence can be shown
 * wherever the step is offered — rail, tooltip, forward button.
 */
export type StepLocks = Record<Step, string | null>

/**
 * The gate, derived from state alone. Step 2 needs a complete profile (a draft
 * with holes would run the core as a baseline nobody decided); steps 3-5 need
 * the engine run. Signing closes nothing — the whole flow stays readable, which
 * is what makes the record auditable.
 */
export function stepLocksFor(input: {
  /** A started draft — parsed from the description or opened by hand. */
  hasDraft: boolean
  missing: string[]
  candidates: CandidatesResponse | null
}): StepLocks {
  const profileReady = !input.hasDraft
    ? 'Primero describe el activo en el paso 1: todo lo demás se compone sobre su ficha.'
    : input.missing.length > 0
      ? `Falta(n) ${input.missing.length} dato(s) por rellenar en la ficha del activo (paso 1).`
      : null
  const composing =
    profileReady ??
    (input.candidates === null
      ? 'Todavía no hay opciones calculadas: pasa por el paso 2 y espera a que el sistema las calcule.'
      : null)

  return { 1: null, 2: profileReady, 3: composing, 4: composing, 5: composing }
}

/**
 * Where the profile came from. No third source and no picker of frozen profiles:
 * the asset is described here from scratch. `manual` is the PRD's fallback for a
 * machine without the model — the same draft, filled in by hand.
 */
export type ProfileSource = 'parse' | 'manual'

/** The region pair, in each order. The order asks a different question. */
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
  /** Ignores a locked step: the gate is enforced here, not only in the rail. */
  goToStep: (step: Step) => void
  stepLocks: StepLocks
  zoneId: string | null
  setZoneId: (zoneId: string) => void
  focusRequest: string | null
  /**
   * The card a `focusOn` sent the operator to, kept after the scroll is done.
   * `focusRequest` lives for one scroll and is cleared by the stage; a card that
   * must also *open* needs the destination readable on the next render, so it is
   * recorded separately.
   */
  expandRequest: string | null
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
  runParse: () => Promise<void>
  /** The PRD's declared fallback: an empty draft the operator fills in by hand. */
  startManualDraft: () => void
  correctTargetSL: (zoneIndex: number, value: number) => void
  correctSL: (zoneIndex: number, requirement: FoundationalRequirement) => void
  correctNature: (zoneIndex: number, field: NatureField) => void
  correctCriticality: (scale: ConsequenceScale) => void
  /**
   * Any other edit to the draft, as a recipe over a copy of it. The typed helpers
   * above cover the fields with their own affordance; the rest are ordinary inputs
   * that a per-field action would not describe any better than the recipe does.
   */
  patchDraft: (
    recipe: (draft: AssetProfileDraft) => void,
    correction?: { path: string; from: unknown; to: unknown },
  ) => void

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

  // --- stage 3: the regional delta over the asset being composed -------------
  delta: RegionalDelta | null
  deltaLoading: boolean
  deltaError: string | null
  deltaOrder: number
  setDeltaOrder: (index: number) => void
  /** How the readings relate and what differentiates them — the human's question. */
  deltaMode: DeltaMode
  setDeltaMode: (mode: DeltaMode) => void
  deltaRegime: DeltaRegime
  setDeltaRegime: (regime: DeltaRegime) => void
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
 * Four layers can declare one — resolution, gating, prioritisation, retrieval —
 * and a capability with no candidate must carry one from at least one (invariant 2).
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

/** How much the operator's current selection covers, and what it cannot weigh. */
export interface PickedCoverage {
  value: number
  /** Picked controls that carry no weight — listed, never counted as zero. */
  unweighted: string[]
}

/**
 * The engine's coverage formula over the subset the human picked — the one figure
 * the client computes, because selections stay in the browser until compose. It is
 * provisional; the number that reaches the baseline is the engine's. Three rules
 * mirror `resolve_capability`: best option not the sum (`max(coverage_weight)`);
 * a contextual overlay weighs nothing (an exigency, not a mechanism); a superseded
 * option the human picked does count (overriding the rule set is a supported move).
 * Retrieved suggestions carry a score and no weight, so they go to `unweighted` —
 * named on screen, never rounded to nothing (invariant 2).
 */
export function pickedCoverage(
  capability: CapabilityCandidates,
  picked: string[],
): PickedCoverage {
  let value = 0
  const unweighted: string[] = []

  for (const controlId of picked) {
    const option = capability.resolution.options.find((o) => o.control.id === controlId)
    if (!option || option.mapping.type === 'contextual') {
      unweighted.push(controlId)
      continue
    }
    value = Math.max(value, option.mapping.coverage_weight)
  }

  return { value, unweighted }
}
