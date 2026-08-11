/**
 * What the operator has done, persisted across visits (UCM-21).
 *
 * Only their side of it: engine answers are re-read, never cached here.
 */

import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'

import type { AssetProfileDraft, ParseResult } from '../api/types'
import type { Correction, ProfileSource, Step } from './composition'

// Versioned: a shape change must not resurrect a half-read composition.
const STORAGE_KEY = 'mfhe.session.v1'

export interface SessionState {
  startedAt: string | null
  updatedAt: string | null

  step: Step
  zoneId: string | null

  source: ProfileSource
  description: string
  descriptionLocked: boolean
  parseResult: ParseResult | null
  draft: AssetProfileDraft | null
  corrections: Correction[]

  selections: Record<string, string[]>
  reasons: Record<string, string>
  gaps: Record<string, boolean>

  // Set on signing. Ends the draft: the screen stays, the next boot does not
  // resume it and re-run the engine to repopulate it.
  signedBaselineId: string | null
}

export interface SessionActions {
  setStep: (step: Step) => void
  setZoneId: (zoneId: string | null) => void

  setDescription: (value: string) => void
  unlockDescription: () => void
  startParsed: (result: ParseResult, draft: AssetProfileDraft) => void
  /** The PRD's declared fallback: the same draft, filled in by hand. */
  startManual: (draft: AssetProfileDraft) => void
  setDraft: (draft: AssetProfileDraft) => void
  recordCorrection: (path: string, from: unknown, to: unknown) => void

  toggleSelection: (key: string, controlId: string) => void
  setReason: (key: string, value: string) => void
  toggleGap: (key: string) => void

  markSigned: (baselineId: string) => void
  reset: () => void
}

const EMPTY: SessionState = {
  startedAt: null,
  updatedAt: null,
  step: 1,
  zoneId: null,
  source: 'parse',
  description: '',
  descriptionLocked: false,
  parseResult: null,
  draft: null,
  corrections: [],
  selections: {},
  reasons: {},
  gaps: {},
  signedBaselineId: null,
}

function touched(state: SessionState): Pick<SessionState, 'startedAt' | 'updatedAt'> {
  const now = new Date().toISOString()
  return { startedAt: state.startedAt ?? now, updatedAt: now }
}

export const useSession = create<SessionState & SessionActions>()(
  persist(
    (set) => ({
      ...EMPTY,

      setStep: (step) => set((state) => ({ ...touched(state), step })),
      setZoneId: (zoneId) => set((state) => ({ ...touched(state), zoneId })),

      setDescription: (description) => set((state) => ({ ...touched(state), description })),
      unlockDescription: () => set((state) => ({ ...touched(state), descriptionLocked: false })),

      startParsed: (parseResult, draft) =>
        set((state) => ({
          ...touched(state),
          source: 'parse',
          parseResult,
          draft,
          corrections: [],
          descriptionLocked: true,
        })),

      startManual: (draft) =>
        set((state) => ({
          ...touched(state),
          source: 'manual',
          parseResult: null,
          draft,
          corrections: [],
          descriptionLocked: false,
        })),

      setDraft: (draft) => set((state) => ({ ...touched(state), draft })),

      recordCorrection: (path, from, to) =>
        set((state) => {
          const rest = state.corrections.filter((correction) => correction.path !== path)
          const undone = String(from) === String(to)
          return {
            ...touched(state),
            corrections: undone ? rest : [...rest, { path, from: String(from), to: String(to) }],
          }
        }),

      // Adopting a mechanism and accepting the gap say opposite things, and the
      // server refuses the pair (`_check_coherent`). Each clears the other.
      toggleSelection: (key, controlId) =>
        set((state) => {
          const picked = state.selections[key] ?? []
          return {
            ...touched(state),
            selections: {
              ...state.selections,
              [key]: picked.includes(controlId)
                ? picked.filter((id) => id !== controlId)
                : [...picked, controlId],
            },
            gaps: { ...state.gaps, [key]: false },
          }
        }),

      setReason: (key, value) =>
        set((state) => ({ ...touched(state), reasons: { ...state.reasons, [key]: value } })),

      toggleGap: (key) =>
        set((state) => {
          const accepted = !(state.gaps[key] ?? false)
          return {
            ...touched(state),
            gaps: { ...state.gaps, [key]: accepted },
            selections: accepted ? { ...state.selections, [key]: [] } : state.selections,
          }
        }),

      markSigned: (signedBaselineId) => set((state) => ({ ...touched(state), signedBaselineId })),

      reset: () => set({ ...EMPTY }),
    }),
    {
      name: STORAGE_KEY,
      storage: createJSONStorage(() => localStorage),
      version: 1,
      partialize: (state): SessionState => ({
        startedAt: state.startedAt,
        updatedAt: state.updatedAt,
        step: state.step,
        zoneId: state.zoneId,
        source: state.source,
        description: state.description,
        descriptionLocked: state.descriptionLocked,
        parseResult: state.parseResult,
        draft: state.draft,
        corrections: state.corrections,
        selections: state.selections,
        reasons: state.reasons,
        gaps: state.gaps,
        signedBaselineId: state.signedBaselineId,
      }),
      onRehydrateStorage: () => (state) => {
        if (state?.signedBaselineId) state.reset()
      },
    },
  ),
)

/** A composition the operator could go back to: started, and not yet signed. */
export function isResumable(state: SessionState): boolean {
  return state.signedBaselineId === null && (state.draft !== null || state.description.trim() !== '')
}
