/**
 * One page of a long list.
 *
 * Paging is a reading aid over a list the engine already returned in full, so
 * every count on screen stays the count of the whole list — the same rule the
 * option folds follow in `CapabilityCard`. Nothing here filters, sorts or drops:
 * it slices.
 *
 * The page is derived rather than reset from an effect. `resetKey` sends the
 * reader back to the first page when the list underneath became a *different*
 * list — another zone, another actor filter — rather than the same one grown by
 * a row, and the length is watched for the same reason: page 3 of a list that
 * now has four entries is a blank screen.
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
