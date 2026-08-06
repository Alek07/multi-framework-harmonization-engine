/**
 * The state of a composition session — the human's side of it, and only that.
 *
 * Every call to the five endpoints lives here, so there is exactly one place
 * that talks to the engine and one place that holds what the operator decided.
 * The arithmetic in `progress` mirrors `_check_mandates`
 * (`server/app/baseline/service.py`) and nothing else: it decides whether the
 * *button* is enabled, and the server verifies the same thing again before
 * signing — so a client that got it wrong could only ever be wrong in the
 * direction of asking, never of signing.
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
} from '../api/client'
import type {
  AssetProfileDraft,
  BaselineAuditLog,
  CandidatesResponse,
  ComposedBaseline,
  CompositionChoice,
  ConsequenceScale,
  FoundationalRequirement,
  NatureField,
  ParseResult,
  RegionalDelta,
  Signature,
} from '../api/types'
import { cloneDraft, emptyZone, missingRequired, toProfile } from '../lib/draft'
import {
  CompositionContext,
  DELTA_ORDERS,
  emptyZoneProgress,
  keyOf,
  stepLocksFor,
  type Blocker,
  type CompositionApi,
  type Correction,
  type ProfileSource,
  type Progress,
  type Step,
  type ZoneProgress,
} from './composition'

function messageOf(error: unknown): string {
  if (error instanceof ApiError || error instanceof OfflineError) return error.message
  return 'Ha ocurrido un error inesperado. Vuelve a intentarlo.'
}

export function CompositionProvider({ children }: { children: ReactNode }) {
  const [backendUp, setBackendUp] = useState<boolean | null>(null)
  const [requestedStep, setStep] = useState<Step>(1)
  const [zoneId, setZoneIdState] = useState<string | null>(null)
  const [focusRequest, setFocusRequest] = useState<string | null>(null)
  const [expandRequest, setExpandRequest] = useState<string | null>(null)

  const [source, setSource] = useState<ProfileSource>('parse')
  const [description, setDescription] = useState('')
  const [descriptionLocked, setDescriptionLocked] = useState(false)
  const [parsing, setParsing] = useState(false)
  const [parseError, setParseError] = useState<string | null>(null)
  const [parseResult, setParseResult] = useState<ParseResult | null>(null)
  const [draft, setDraft] = useState<AssetProfileDraft | null>(null)
  const [corrections, setCorrections] = useState<Correction[]>([])

  const [candidates, setCandidates] = useState<CandidatesResponse | null>(null)
  const [candidatesLoading, setCandidatesLoading] = useState(false)
  const [candidatesError, setCandidatesError] = useState<string | null>(null)
  const [explaining, setExplaining] = useState<string | null>(null)

  const [selections, setSelections] = useState<Record<string, string[]>>({})
  const [reasons, setReasons] = useState<Record<string, string>>({})
  const [gaps, setGaps] = useState<Record<string, boolean>>({})

  const [delta, setDelta] = useState<RegionalDelta | null>(null)
  const [deltaLoading, setDeltaLoading] = useState(false)
  const [deltaError, setDeltaError] = useState<string | null>(null)
  const [deltaOrder, setDeltaOrder] = useState(0)

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
      setParseResult(result)
      setDraft(cloneDraft(result.draft))
      setCorrections([])
      setDescriptionLocked(true)
      setSource('parse')
      setCandidates(null)
      setDelta(null)
    } catch (error) {
      setParseError(messageOf(error))
    } finally {
      setParsing(false)
    }
  }, [description, parsing, signed])

  /**
   * The fallback the PRD declares: the same draft, with nothing in it.
   *
   * Every value starts empty rather than defaulted, for the same reason the
   * parse returns nulls: a target SL nobody chose would run through the core and
   * produce a baseline nobody decided. `missing_required` is what tells the
   * operator, path by path, what is still theirs to fill in.
   */
  const startManualDraft = useCallback(() => {
    if (signed) return
    setSource('manual')
    setParseResult(null)
    setCorrections([])
    setDescriptionLocked(false)
    setCandidates(null)
    setDelta(null)
    setDraft({
      name: null,
      case: null,
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

  /** Record a correction against what the model proposed, or drop it if undone. */
  const recordCorrection = useCallback((path: string, from: unknown, to: unknown) => {
    setCorrections((current) => {
      const rest = current.filter((correction) => correction.path !== path)
      if (String(from) === String(to)) return rest
      return [...rest, { path, from: String(from), to: String(to) }]
    })
  }, [])

  const modelDraft = parseResult?.draft ?? null

  const correctTargetSL = useCallback(
    (zoneIndex: number, value: number) => {
      if (signed || !draft) return
      const next = cloneDraft(draft)
      next.zones[zoneIndex].target_sl = value
      setDraft(next)
      recordCorrection(
        `zones[${next.zones[zoneIndex].id}].target_sl`,
        modelDraft?.zones[zoneIndex]?.target_sl ?? '—',
        value,
      )
    },
    [draft, modelDraft, recordCorrection, signed],
  )

  const correctSL = useCallback(
    (zoneIndex: number, requirement: FoundationalRequirement) => {
      if (signed || !draft) return
      const next = cloneDraft(draft)
      const zone = next.zones[zoneIndex]
      const vector = zone.sl_vector ?? {}
      // 1..4, then back to "not stated": an SL the text never gave is a value the
      // operator may legitimately want to leave empty rather than guess.
      const current = vector[requirement]
      const value = current == null ? 1 : current >= 4 ? null : current + 1
      zone.sl_vector = { ...vector, [requirement]: value }
      setDraft(next)
      recordCorrection(
        `zones[${zone.id}].sl_vector.${requirement}`,
        modelDraft?.zones[zoneIndex]?.sl_vector?.[requirement] ?? '—',
        value ?? '—',
      )
    },
    [draft, modelDraft, recordCorrection, signed],
  )

  const correctNature = useCallback(
    (zoneIndex: number, field: NatureField) => {
      if (signed || !draft) return
      const next = cloneDraft(draft)
      const zone = next.zones[zoneIndex]
      const current = zone.nature[field]
      // true -> false -> "the text does not say". The third state stays reachable
      // because a guessed `false` silently removes mechanisms from the baseline.
      zone.nature[field] = current == null ? true : current ? false : null
      setDraft(next)
      recordCorrection(
        `zones[${zone.id}].nature.${field}`,
        modelDraft?.zones[zoneIndex]?.nature?.[field] ?? '—',
        zone.nature[field] ?? '—',
      )
    },
    [draft, modelDraft, recordCorrection, signed],
  )

  const correctCriticality = useCallback(
    (scale: ConsequenceScale) => {
      if (signed || !draft) return
      const next = cloneDraft(draft)
      next.criticality.scale = scale
      setDraft(next)
      recordCorrection('criticality.scale', modelDraft?.criticality.scale ?? '—', scale)
    },
    [draft, modelDraft, recordCorrection, signed],
  )

  const patchDraft = useCallback(
    (
      recipe: (draft: AssetProfileDraft) => void,
      correction?: { path: string; from: unknown; to: unknown },
    ) => {
      if (signed || !draft) return
      const next = cloneDraft(draft)
      recipe(next)
      setDraft(next)
      if (correction) recordCorrection(correction.path, correction.from, correction.to)
    },
    [draft, recordCorrection, signed],
  )

  // --- stage 2 ---------------------------------------------------------------

  /**
   * One engine run at a time.
   *
   * `POST /candidates` is not a read: it appends the run's decisions to the
   * append-only ledger, and the ledger numbers them by reading its own head
   * first. Two overlapping runs therefore claim the same sequence and the
   * second one is refused by the database — correctly, but the operator would
   * see a 500 for having double-clicked. React's development mode double-invokes
   * effects, so this guard is not hypothetical: without it the very first load
   * of the candidates stage fires the run twice.
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
        setZoneIdState((current) => {
          const stillThere = response.zones.some((zone) => zone.zone.zone_id === current)
          return stillThere ? current : (response.zones[0]?.zone.zone_id ?? null)
        })
      } catch (error) {
        setCandidatesError(messageOf(error))
      } finally {
        running.current = false
      }
    },
    [profile],
  )

  const loadCandidates = useCallback(async () => {
    // Same guard as `runCandidates`, and it has to be *here* too: StrictMode
    // invokes the mount effect twice, and a second call that returns without
    // running would otherwise clear the flag while the first request is in
    // flight — leaving the stage with no sign that anything is happening.
    if (running.current) return
    setCandidatesLoading(true)
    try {
      await runCandidates()
    } finally {
      setCandidatesLoading(false)
    }
  }, [runCandidates])

  /**
   * Ask the LLM why each candidate of one capability is on screen (UCM-14).
   *
   * It re-runs `POST /candidates` because that is where the scope lives, and the
   * response replaces the current one: a new engine run, appended to the ledger
   * like any other. The operator's decisions survive it untouched — they are
   * keyed by zone, capability and control, not by run.
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
      const key = keyOf(zone, capabilityId)
      setSelections((current) => {
        const picked = current[key] ?? []
        const next = picked.includes(controlId)
          ? picked.filter((id) => id !== controlId)
          : [...picked, controlId]
        return { ...current, [key]: next }
      })
      // Adopting a mechanism and accepting the gap say opposite things; the
      // server refuses the pair, so the UI never offers it (`_check_coherent`).
      setGaps((current) => ({ ...current, [key]: false }))
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
      setReasons((current) => ({ ...current, [keyOf(zone, capabilityId)]: value }))
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
      const key = keyOf(zone, capabilityId)
      setGaps((current) => {
        const next = !(current[key] ?? false)
        if (next) setSelections((picked) => ({ ...picked, [key]: [] }))
        return { ...current, [key]: next }
      })
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
   * The human's decisions, in the four kinds the ledger knows how to file.
   *
   * `compensatory_declared` is not a separate control in the interface: a
   * mechanism that gating listed as compensatory for this capability *is* a
   * compensatory declaration, and filing it as an ordinary selection would put
   * the wrong sentence in the trail.
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
        // recorded without its justification is the thing UCM-11 forbids.
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
        }),
      )
    } catch (error) {
      setDelta(null)
      setDeltaError(messageOf(error))
    } finally {
      setDeltaLoading(false)
    }
  }, [deltaOrder, profile, zoneId])

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
        try {
          setAuditLog(await fetchAuditLog(composed.baseline_id))
          setAuditLogError(null)
        } catch (error) {
          setAuditLogError(messageOf(error))
        }
        setStep(5)
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
   * A step whose input disappears cannot stay on screen.
   *
   * Re-parsing the description or starting a manual draft clears the engine run,
   * and the operator may be standing on a step that reads it. The step is derived
   * rather than stored for that reason: what is on screen is always a step that
   * still holds, without a render passing through one that does not.
   */
  const step = stepLocks[requestedStep]
    ? (([4, 3, 2, 1] as Step[]).find((n) => n < requestedStep && !stepLocks[n]) ?? 1)
    : requestedStep

  const goToStep = useCallback(
    (next: Step) => {
      if (stepLocks[next]) return
      setStep(next)
      window.scrollTo({ top: 0, behavior: 'smooth' })
    },
    [stepLocks],
  )

  const setZoneId = useCallback((next: string) => setZoneIdState(next), [])

  const focusOn = useCallback(
    (domId: string, zone: string, next: Step) => {
      if (stepLocks[next]) return
      setZoneIdState(zone)
      setStep(next)
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
    setDescription,
    descriptionLocked,
    unlockDescription: () => setDescriptionLocked(false),
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
