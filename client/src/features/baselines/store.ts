/** The signed baselines, as the server lists them. Never cached to disk. */

import { create } from 'zustand'

import { ApiError, OfflineError, catalogVersion, fetchBaselines } from '../../api/client'
import type { BaselineSummary } from '../../api/types'

interface BaselinesState {
  baselines: BaselineSummary[]
  /** The running catalog version, so the "Catálogo" field has a source with an empty ledger. */
  catalogVersion: string | null
  loading: boolean
  error: string | null
  loaded: boolean
  load: () => Promise<void>
}

export const useBaselines = create<BaselinesState>()((set, get) => ({
  baselines: [],
  catalogVersion: null,
  loading: false,
  error: null,
  loaded: false,

  load: async () => {
    if (get().loading) return
    set({ loading: true, error: null })
    // Best-effort and independent of the list: a blank field, never a failed load.
    void catalogVersion().then((version) => version && set({ catalogVersion: version }))
    try {
      const list = await fetchBaselines()
      set({ baselines: list.baselines, loaded: true })
    } catch (error) {
      set({
        error:
          error instanceof ApiError || error instanceof OfflineError
            ? error.message
            : 'No se ha podido leer la lista de líneas base.',
      })
    } finally {
      set({ loading: false })
    }
  },
}))
