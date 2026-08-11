/** The signed baselines, as the server lists them. Never cached to disk. */

import { create } from 'zustand'

import { ApiError, OfflineError, fetchBaselines } from '../../api/client'
import type { BaselineSummary } from '../../api/types'

interface BaselinesState {
  baselines: BaselineSummary[]
  loading: boolean
  error: string | null
  loaded: boolean
  load: () => Promise<void>
}

export const useBaselines = create<BaselinesState>()((set, get) => ({
  baselines: [],
  loading: false,
  error: null,
  loaded: false,

  load: async () => {
    if (get().loading) return
    set({ loading: true, error: null })
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
