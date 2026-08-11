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
} from '../../api/types'

export type Step = 1 | 2 | 3 | 4 | 5

/**
 * Why each step is not reachable yet, or `null` when it is.
 *
 * The five steps are one argument told in order, and a step whose input does not
 * exist yet has nothing honest to show: the candidates screen with no profile,
 * the regional comparison with no zones, the trail before a single decision. The
 * locks say *what is missing* rather than merely refusing, so the sentence is
 * shown wherever the step is offered — rail, tooltip, forward button.
 */
export type StepLocks = Record<Step, string | null>

/**
 * The gate, derived from the state and nothing else.
 *
 * Step 2 needs a complete profile — a draft with holes in it would run through
 * the core as a baseline nobody decided. Steps 3 to 5 need the engine run: they
 * all read `CandidatesResponse`, and the trail of step 5 shows the decisions
 * taken over it. Signing does not close anything: after it the whole flow stays
 * readable, which is what makes the record auditable.
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
 * Where the profile came from.
 *
 * There is no third source, and in particular there is no picker of profiles
 * frozen in the repository: the asset is described here, from scratch, which is
 * what the engine is for. `manual` is the fallback the PRD declares for a
 * machine where the model is not available — the same draft, filled in by hand.
 */
export type ProfileSource = 'parse' | 'manual'

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
  /** Ignores a locked step: the gate is enforced here, not only in the rail. */
  goToStep: (step: Step) => void
  stepLocks: StepLocks
  zoneId: string | null
  setZoneId: (zoneId: string) => void
  focusRequest: string | null
  /**
   * The card a `focusOn` sent the operator to, kept after the scroll is done.
   *
   * `focusRequest` lives for exactly one scroll and is cleared by the stage that
   * performs it. A capability card that also has to *open* needs the request to
   * still be readable on the render after that, so the destination is recorded
   * separately: a blocker in step 4 that lands the operator on a closed header
   * would be answering the link with the question again.
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
   * Any other edit to the draft, as a recipe over a copy of it.
   *
   * The typed helpers above cover the fields with their own affordance (the SL
   * grid, the tri-state nature, the criticality scale). The rest — the asset's
   * name and case, the zones' ids, the free-text criticality fields, adding and
   * removing zones and conduits — are ordinary inputs, and giving each one its
   * own action in this contract would say nothing the recipe does not.
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

/** How much the operator's current selection covers, and what it cannot weigh. */
export interface PickedCoverage {
  value: number
  /** Picked controls that carry no weight — listed, never counted as zero. */
  unweighted: string[]
}

/**
 * The engine's own coverage formula, applied to the subset the human picked.
 *
 * This is the one figure the client computes, and it exists because selections
 * never leave the browser until `POST /baseline/compose`: between the engine's
 * answer and the signature there is nobody else who could report what the
 * composition covers. It is provisional by construction — the number that
 * reaches the baseline and the trail is the engine's, computed at compose time.
 *
 * Three decisions, and each one mirrors `resolve_capability` on purpose:
 *
 * * **The best option, not the sum.** The core takes `max(coverage_weight)`
 *   over the effective options; adding two partial mechanisms together would
 *   claim a coverage the engine never grants, on the screen where the operator
 *   decides whether the requirement is answered.
 * * **A contextual overlay weighs nothing.** The core leaves it out of coverage
 *   because a jurisdictional obligation is an exigency, not a mechanism, and
 *   choosing one does not implement anything.
 * * **A superseded option the human picked does count** — and here the mirror
 *   is deliberately broken. The core drops it because its rule set set it
 *   aside; overriding that is a supported move with its own written reason, and
 *   once the operator takes it, it is their mechanism and covers what it covers.
 *
 * Retrieved suggestions carry a similarity score and no weight — that is the
 * retriever's contract, not an omission — so picking one is a real decision
 * with an unquantifiable contribution. It goes to `unweighted`, to be named on
 * screen rather than silently rounded to nothing (invariant 2).
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
