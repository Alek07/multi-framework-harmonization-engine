/**
 * The human's side of a composition session, and the single place that calls the
 * engine. The arithmetic in `progress` mirrors `_check_mandates` only to enable
 * the *button*; the server re-verifies before signing, so a wrong client can only
 * err toward asking, never toward signing. What the operator decided lives in
 * `session.ts` and outlives the tab; engine answers stay here and die with the page.
 */

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'

import {
  ApiError,
  OfflineError,
  composeBaseline,
  fetchAuditLog,
  fetchCandidates,
  fetchDelta,
  health,
  parseAsset,
  profileRef,
} from '../../api/client'
import type {
  AssetProfileDraft,
  BaselineAuditLog,
  CandidatesResponse,
  ComposedBaseline,
  CompositionChoice,
  ConsequenceScale,
  DeltaMode,
  DeltaRegime,
  FoundationalRequirement,
  NatureField,
  RegionalDelta,
  Signature,
} from '../../api/types'
import { cloneDraft, emptyZone, missingRequired, toProfile } from '../../lib/draft'
import {
  CompositionContext,
  DELTA_ORDERS,
  emptyZoneProgress,
  keyOf,
  stepLocksFor,
  type Blocker,
  type CompositionApi,
  type Progress,
  type Step,
  type ZoneProgress,
} from './composition'
import { useSession } from './session'

function messageOf(error: unknown): string {
  if (error instanceof ApiError || error instanceof OfflineError) return error.message
  return 'Ha ocurrido un error inesperado. Vuelve a intentarlo.'
}

export function CompositionProvider({ children }: { children: ReactNode }) {
  // Persisted: the same object across a reload.
  const session = useSession()
  const {
    step: requestedStep,
    zoneId,
    source,
    description,
    descriptionLocked,
    parseResult,
    draft,
    corrections,
    selections,
    reasons,
    gaps,
  } = session

  // The engine's answers and the screen's own state. Neither outlives the page.
  const [backendUp, setBackendUp] = useState<boolean | null>(null)
  const [focusRequest, setFocusRequest] = useState<string | null>(null)
  const [expandRequest, setExpandRequest] = useState<string | null>(null)

  const [parsing, setParsing] = useState(false)
  const [parseError, setParseError] = useState<string | null>(null)

  const [candidates, setCandidates] = useState<CandidatesResponse | null>(null)
  const [candidatesLoading, setCandidatesLoading] = useState(false)
  const [candidatesError, setCandidatesError] = useState<string | null>(null)
  const [explaining, setExplaining] = useState<string | null>(null)

  const [delta, setDelta] = useState<RegionalDelta | null>(null)
  const [deltaLoading, setDeltaLoading] = useState(false)
  const [deltaError, setDeltaError] = useState<string | null>(null)
  const [deltaOrder, setDeltaOrder] = useState(0)
  // Opens symmetric (both directions) and legal (law against law): the screen
  // answers one question, the difference between the regimes governing this asset.
  const [deltaMode, setDeltaMode] = useState<DeltaMode>('symmetric')
  const [deltaRegime, setDeltaRegime] = useState<DeltaRegime>('legal')

  const [signing, setSigning] = useState(false)
  const [signError, setSignError] = useState<string | null>(null)
  const [baseline, setBaseline] = useState<ComposedBaseline | null>(null)
  const [auditLog, setAuditLog] = useState<BaselineAuditLog | null>(null)
  const [auditLogError, setAuditLogError] = useState<string | null>(null)

  const signed = baseline !== null

  useEffect(() => {
    void health().then(setBackendUp)
  }, [])

  // --- stage 1 ---------------------------------------------------------------

  const missing = useMemo(() => (draft ? missingRequired(draft) : []), [draft])
  const profile = useMemo(
    () => (draft ? toProfile(draft, parseResult?.profile_id ?? null) : null),
    [draft, parseResult],
  )

  const runParse = useCallback(async () => {
    if (signed || parsing || !description.trim()) return
    setParsing(true)
    setParseError(null)
    try {
      const result = await parseAsset({ description })
      useSession.getState().startParsed(result, cloneDraft(result.draft))
      setCandidates(null)
      setDelta(null)
    } catch (error) {
      setParseError(messageOf(error))
    } finally {
      setParsing(false)
    }
  }, [description, parsing, signed])

  /**
   * The PRD's fallback: the same draft, empty. Every value starts empty rather
   * than defaulted (like the parse's nulls) — a target SL nobody chose would run
   * the core into a baseline nobody decided. `missing_required` lists what is left.
   */
  const startManualDraft = useCallback(() => {
    if (signed) return
    setCandidates(null)
    setDelta(null)
    useSession.getState().startManual({
      name: null,
      case: null,
      sectors: [],
      zones: [emptyZone('Z-1')],
      conduits: [],
      criticality: {
        physical_consequence: null,
        scale: null,
        threat_model: null,
        consequence_path: null,
        attack_reference: null,
      },
      notes: [],
      unmapped: [],
    })
  }, [signed])

  const modelDraft = parseResult?.draft ?? null

  /** One edit to the draft and the correction it records, applied together. */
  const correct = useCallback(
    (
      recipe: (draft: AssetProfileDraft) => void,
      correction?: { path: string; from: unknown; to: unknown },
    ) => {
      if (signed || !draft) return
      const next = cloneDraft(draft)
      recipe(next)
      const store = useSession.getState()
      store.setDraft(next)
      if (correction) store.recordCorrection(correction.path, correction.from, correction.to)
    },
    [draft, signed],
  )

  const correctTargetSL = useCallback(
    (zoneIndex: number, value: number) => {
      const zone = draft?.zones[zoneIndex]
      if (!zone) return
      correct(
        (next) => {
          next.zones[zoneIndex].target_sl = value
        },
        {
          path: `zones[${zone.id}].target_sl`,
          from: modelDraft?.zones[zoneIndex]?.target_sl ?? '—',
          to: value,
        },
      )
    },
    [correct, draft, modelDraft],
  )

  const correctSL = useCallback(
    (zoneIndex: number, requirement: FoundationalRequirement) => {
      const zone = draft?.zones[zoneIndex]
      if (!zone) return
      // 1..4, then back to "not stated": an SL the text never gave is a value the
      // operator may legitimately want to leave empty rather than guess.
      const current = zone.sl_vector?.[requirement]
      const value = current == null ? 1 : current >= 4 ? null : current + 1
      correct(
        (next) => {
          const target = next.zones[zoneIndex]
          target.sl_vector = { ...(target.sl_vector ?? {}), [requirement]: value }
        },
        {
          path: `zones[${zone.id}].sl_vector.${requirement}`,
          from: modelDraft?.zones[zoneIndex]?.sl_vector?.[requirement] ?? '—',
          to: value ?? '—',
        },
      )
    },
    [correct, draft, modelDraft],
  )

  const correctNature = useCallback(
    (zoneIndex: number, field: NatureField) => {
      const zone = draft?.zones[zoneIndex]
      if (!zone) return
      // true -> false -> "the text does not say". The third state stays reachable
      // because a guessed `false` silently removes mechanisms from the baseline.
      const current = zone.nature[field]
      const value = current == null ? true : current ? false : null
      correct(
        (next) => {
          next.zones[zoneIndex].nature[field] = value
        },
        {
          path: `zones[${zone.id}].nature.${field}`,
          from: modelDraft?.zones[zoneIndex]?.nature?.[field] ?? '—',
          to: value ?? '—',
        },
      )
    },
    [correct, draft, modelDraft],
  )

  const correctCriticality = useCallback(
    (scale: ConsequenceScale) => {
      correct(
        (next) => {
          next.criticality.scale = scale
        },
        {
          path: 'criticality.scale',
          from: modelDraft?.criticality.scale ?? '—',
          to: scale,
        },
      )
    },
    [correct, modelDraft],
  )

  const patchDraft = correct

  // --- stage 2 ---------------------------------------------------------------

  /**
   * One engine run at a time. `POST /candidates` appends to the append-only
   * ledger, which numbers entries from its own head, so two overlapping runs
   * claim the same sequence and the second is refused. StrictMode double-invokes
   * effects, so without this guard the first candidates load fires the run twice.
   */
  const running = useRef(false)

  const runCandidates = useCallback(
    async (explain?: { zone_id: string; capability_ids: string[] }) => {
      if (running.current) return
      if (!profile) return
      running.current = true
      setCandidatesError(null)
      try {
        const response = await fetchCandidates({
          ...profileRef(profile, null),
          retrieval: true,
          ...(explain ? { explain } : {}),
        })
        setCandidates(response)
        // From the store, not a closure: the zone may have moved during the await.
        const store = useSession.getState()
        const stillThere = response.zones.some((zone) => zone.zone.zone_id === store.zoneId)
        if (!stillThere) store.setZoneId(response.zones[0]?.zone.zone_id ?? null)
      } catch (error) {
        setCandidatesError(messageOf(error))
      } finally {
        running.current = false
      }
    },
    [profile],
  )

  const loadCandidates = useCallback(async () => {
    // Guard needed here too: StrictMode invokes the mount effect twice, and a
    // second call clearing the flag mid-flight would leave the stage looking idle.
    if (running.current) return
    setCandidatesLoading(true)
    try {
      await runCandidates()
    } finally {
      setCandidatesLoading(false)
    }
  }, [runCandidates])

  /**
   * Ask the LLM why each candidate of one capability is on screen. Re-runs
   * `POST /candidates` (where the scope lives), replacing the current response.
   * The operator's decisions survive: they are keyed by zone/capability/control,
   * not by run.
   */
  const explainCapability = useCallback(
    async (zone: string, capabilityId: string) => {
      if (signed || explaining) return
      setExplaining(keyOf(zone, capabilityId))
      await runCandidates({ zone_id: zone, capability_ids: [capabilityId] })
      setExplaining(null)
    },
    [explaining, runCandidates, signed],
  )

  // --- the human's decisions -------------------------------------------------

  const selectionsFor = useCallback(
    (zone: string, capabilityId: string) => selections[keyOf(zone, capabilityId)] ?? [],
    [selections],
  )

  const toggleSelection = useCallback(
    (zone: string, capabilityId: string, controlId: string) => {
      if (signed) return
      useSession.getState().toggleSelection(keyOf(zone, capabilityId), controlId)
    },
    [signed],
  )

  const reasonFor = useCallback(
    (zone: string, capabilityId: string) => reasons[keyOf(zone, capabilityId)] ?? '',
    [reasons],
  )

  const setReason = useCallback(
    (zone: string, capabilityId: string, value: string) => {
      if (signed) return
      useSession.getState().setReason(keyOf(zone, capabilityId), value)
    },
    [signed],
  )

  const gapAccepted = useCallback(
    (zone: string, capabilityId: string) => gaps[keyOf(zone, capabilityId)] ?? false,
    [gaps],
  )

  const toggleGap = useCallback(
    (zone: string, capabilityId: string) => {
      if (signed) return
      useSession.getState().toggleGap(keyOf(zone, capabilityId))
    },
    [signed],
  )

  // --- where the composition stands, as the engine reported it ---------------

  const progress = useMemo<Progress>(() => {
    const blockers: Blocker[] = []
    const byZone: Record<string, ZoneProgress> = {}
    const total = emptyZoneProgress()

    for (const zone of candidates?.zones ?? []) {
      const zid = zone.zone.zone_id
      const stats = emptyZoneProgress()
      byZone[zid] = stats

      for (const capability of zone.capabilities) {
        const key = keyOf(zid, capability.capability_id)
        const picked = selections[key] ?? []
        const accepted = gaps[key] ?? false
        const reason = (reasons[key] ?? '').trim()
        const decided = picked.length > 0 || accepted
        const gap =
          capability.resolution.gap ??
          capability.gating.gap ??
          capability.priority.gap ??
          capability.retrieval?.gap ??
          null

        if (gap) {
          stats.gaps += 1
          if (accepted) stats.gapsAcknowledged += 1
        }

        if (capability.priority.tier === 'tier_0') {
          stats.tier0Total += 1
          if (!capability.priority.outstanding || decided) stats.tier0Done += 1
        }

        if (signed) continue

        // Exactly the server's own list of what must be closed before a
        // signature is admissible: a Tier 0 capability the engine could not
        // close on its own (`CapabilityPriority.outstanding`).
        if (capability.priority.outstanding && !decided) {
          blockers.push({
            text: `Requisito obligatorio sin decidir: «${capability.capability_name}» en la zona ${zid}`,
            zoneId: zid,
            capabilityId: capability.capability_id,
          })
        }
        // A decision without a written justification is not a decision: the
        // ledger refuses a blank `rationale`.
        if (decided && !reason) {
          blockers.push({
            text: `Falta escribir por qué has decidido «${capability.capability_name}» en la zona ${zid}`,
            zoneId: zid,
            capabilityId: capability.capability_id,
          })
        }
      }

      for (const conflict of zone.open_decisions) {
        const picked = selections[keyOf(zid, conflict.capability_id)] ?? []
        if (conflict.control_ids.some((id) => picked.includes(id))) continue
        stats.conflictsOpen += 1
        if (!signed) {
          blockers.push({
            text: `Conflicto pendiente de tu decisión en «${conflict.capability_id}», zona ${zid}`,
            zoneId: zid,
            capabilityId: conflict.capability_id,
          })
        }
      }

      total.tier0Done += stats.tier0Done
      total.tier0Total += stats.tier0Total
      total.gaps += stats.gaps
      total.gapsAcknowledged += stats.gapsAcknowledged
      total.conflictsOpen += stats.conflictsOpen
    }

    return { ...total, blockers, byZone }
  }, [candidates, gaps, reasons, selections, signed])

  /**
   * The human's decisions in the four kinds the ledger files. `compensatory_declared`
   * is not a separate control: a mechanism gating listed as compensatory *is* a
   * compensatory declaration, and filing it as a plain selection would mislabel the trail.
   */
  const choices = useMemo<CompositionChoice[]>(() => {
    const built: CompositionChoice[] = []

    for (const zone of candidates?.zones ?? []) {
      const zid = zone.zone.zone_id
      const contested = new Map<string, string[]>()
      for (const conflict of zone.open_decisions) {
        contested.set(conflict.capability_id, conflict.control_ids)
      }

      for (const capability of zone.capabilities) {
        const key = keyOf(zid, capability.capability_id)
        const picked = selections[key] ?? []
        const reason = (reasons[key] ?? '').trim()
        // No reason, no entry: the request would be refused, and a decision
        // recorded without its justification is exactly what is forbidden.
        if (!reason) continue

        for (const controlId of picked) {
          built.push({
            kind: capability.gating.compensatory_control_ids.includes(controlId)
              ? 'compensatory_declared'
              : 'option_selected',
            zone_id: zid,
            capability_id: capability.capability_id,
            control_id: controlId,
            rationale: reason,
          })
        }

        // Settling a contradiction says two things: this one prevails, and that
        // one does not. Both go on the record, or the trail would not show that
        // the human decided the conflict at all.
        const inConflict = contested.get(capability.capability_id) ?? []
        if (inConflict.some((id) => picked.includes(id))) {
          for (const controlId of inConflict) {
            if (picked.includes(controlId)) continue
            built.push({
              kind: 'option_rejected',
              zone_id: zid,
              capability_id: capability.capability_id,
              control_id: controlId,
              rationale: reason,
            })
          }
        }

        if (gaps[key]) {
          built.push({
            kind: 'gap_accepted',
            zone_id: zid,
            capability_id: capability.capability_id,
            rationale: reason,
          })
        }
      }
    }

    return built
  }, [candidates, gaps, reasons, selections])

  // --- stage 3 ---------------------------------------------------------------

  const loadDelta = useCallback(async () => {
    if (!profile || !zoneId) return
    setDeltaLoading(true)
    setDeltaError(null)
    try {
      setDelta(
        await fetchDelta({
          regions: DELTA_ORDERS[deltaOrder].regions,
          profile,
          zoneId,
          mode: deltaMode,
          regime: deltaRegime,
        }),
      )
    } catch (error) {
      setDelta(null)
      setDeltaError(messageOf(error))
    } finally {
      setDeltaLoading(false)
    }
  }, [deltaOrder, deltaMode, deltaRegime, profile, zoneId])

  // --- stages 4 and 5 --------------------------------------------------------

  const sign = useCallback(
    async (signature: Signature): Promise<boolean> => {
      if (!candidates || signing || signed) return false
      setSigning(true)
      setSignError(null)
      try {
        const composed = await composeBaseline({
          run_id: candidates.run_id,
          ...profileRef(profile, null),
          choices,
          signature,
        })
        setBaseline(composed)
        // Ends the draft: read-only from here, and not resumed on the next visit.
        useSession.getState().markSigned(composed.baseline_id)
        try {
          setAuditLog(await fetchAuditLog(composed.baseline_id))
          setAuditLogError(null)
        } catch (error) {
          setAuditLogError(messageOf(error))
        }
        useSession.getState().setStep(5)
        return true
      } catch (error) {
        setSignError(messageOf(error))
        return false
      } finally {
        setSigning(false)
      }
    },
    [candidates, choices, profile, signing, signed],
  )

  // --- navigation ------------------------------------------------------------

  const stepLocks = useMemo(
    () => stepLocksFor({ hasDraft: draft !== null, missing, candidates }),
    [candidates, draft, missing],
  )

  /**
   * A step whose input disappears cannot stay on screen. Re-parsing or starting a
   * manual draft clears the engine run, so the step is derived rather than stored:
   * what shows is always a step that still holds.
   */
  const step = stepLocks[requestedStep]
    ? (([4, 3, 2, 1] as Step[]).find((n) => n < requestedStep && !stepLocks[n]) ?? 1)
    : requestedStep

  const goToStep = useCallback(
    (next: Step) => {
      if (stepLocks[next]) return
      useSession.getState().setStep(next)
      window.scrollTo({ top: 0, behavior: 'smooth' })
    },
    [stepLocks],
  )

  const setZoneId = useCallback((next: string) => useSession.getState().setZoneId(next), [])

  const focusOn = useCallback(
    (domId: string, zone: string, next: Step) => {
      if (stepLocks[next]) return
      const store = useSession.getState()
      store.setZoneId(zone)
      store.setStep(next)
      setFocusRequest(domId)
      // Outlives the scroll: whoever is at `domId` may need to open itself, and
      // the scroll request is gone by the render after this one.
      setExpandRequest(domId)
    },
    [stepLocks],
  )

  const clearFocus = useCallback(() => setFocusRequest(null), [])

  const value: CompositionApi = {
    backendUp,
    step,
    goToStep,
    stepLocks,
    zoneId,
    setZoneId,
    focusRequest,
    expandRequest,
    focusOn,
    clearFocus,

    source,
    description,
    setDescription: session.setDescription,
    descriptionLocked,
    unlockDescription: session.unlockDescription,
    parsing,
    parseError,
    parseResult,
    draft,
    corrections,
    missing,
    profile,
    runParse,
    startManualDraft,
    patchDraft,
    correctTargetSL,
    correctSL,
    correctNature,
    correctCriticality,

    candidates,
    candidatesLoading,
    candidatesError,
    loadCandidates,
    explaining,
    explainCapability,

    selectionsFor,
    toggleSelection,
    reasonFor,
    setReason,
    gapAccepted,
    toggleGap,
    choices,
    progress,

    delta,
    deltaLoading,
    deltaError,
    deltaOrder,
    setDeltaOrder,
    deltaMode,
    setDeltaMode,
    deltaRegime,
    setDeltaRegime,
    loadDelta,

    signing,
    signError,
    baseline,
    auditLog,
    auditLogError,
    signed,
    sign,
  }

  return <CompositionContext.Provider value={value}>{children}</CompositionContext.Provider>
}
