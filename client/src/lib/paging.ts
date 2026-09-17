/**
 * One page of a long list — a reading aid over a list the engine returned in full,
 * so every count on screen stays the count of the whole list. Nothing filters,
 * sorts or drops: it slices. The page is derived, not reset from an effect;
 * `resetKey` and the length send the reader to page 1 when the list became a
 * *different* one (another zone, another filter) or shrank below the current page.
 */

import { useState } from 'react'

export interface Page<T> {
  page: number
  setPage: (page: number) => void
  pages: number
  slice: T[]
  /** Zero-based index of the first item shown, for «6–10 de 23». */
  from: number
  to: number
  total: number
}

export function usePage<T>(items: T[], size: number, resetKey?: unknown): Page<T> {
  const [state, setState] = useState({ key: resetKey, count: items.length, page: 0 })

  const stale = state.key !== resetKey || state.count !== items.length
  const pages = Math.max(1, Math.ceil(items.length / size))
  const page = stale ? 0 : Math.min(state.page, pages - 1)
  const from = page * size
  const slice = items.slice(from, from + size)

  return {
    page,
    setPage: (next: number) => setState({ key: resetKey, count: items.length, page: next }),
    pages,
    slice,
    from,
    to: from + slice.length,
    total: items.length,
  }
}
