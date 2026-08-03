/**
 * The five endpoints, and nothing else.
 *
 * Invariant 4 says the API surface is closed. This module is the client-side
 * half of that promise: one axios instance, exactly the five calls of §7.4 plus
 * the liveness probe the Plan B screen reads, and every one of them returns the
 * server's own shape untouched. No call here merges, filters or reorders a
 * response — what the operator sees is what the engine sent.
 */

import axios, { type AxiosInstance, type AxiosRequestConfig } from 'axios'

import type {
  AssetParseRequest,
  AssetProfile,
  BaselineAuditLog,
  CandidatesRequest,
  CandidatesResponse,
  ComposeRequest,
  ComposedBaseline,
  Jurisdiction,
  ParseResult,
  RegionalDelta,
} from './types'

/** `/api/v1` on this origin by default; the dev server proxies it (vite.config.ts). */
const BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

/**
 * Timeouts sized by what the call actually does on the reference machine.
 *
 * The deterministic core is arithmetic over a versioned catalog and answers in
 * milliseconds. One parse is a 7B model decoding on CPU. One explanation batch
 * is ~12 paragraphs of it, which is why the server gives that path its own
 * 600 s budget (`EXPLAIN_TIMEOUT_SECONDS`); a shorter one here would cut off a
 * request the backend is still honouring.
 */
const TIMEOUTS = {
  fast: 60_000,
  parse: 200_000,
  explain: 620_000,
} as const

export class ApiError extends Error {
  readonly status: number
  readonly detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

/** The backend is unreachable, or took longer than the call's budget. */
export class OfflineError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'OfflineError'
  }
}

interface ValidationIssue {
  loc?: (string | number)[]
  msg?: string
}

/**
 * FastAPI answers with `{detail: "..."}` for the engine's own refusals and with
 * `{detail: [{loc, msg}, ...]}` for a body that does not validate. Both are
 * shown to the operator verbatim: the server's refusals are written for them —
 * they name the mandate that is open, the version that moved — and rewriting
 * them here would replace a precise sentence with a vague one.
 */
function detailOf(status: number, body: unknown): string {
  if (typeof body === 'object' && body !== null && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      return (detail as ValidationIssue[])
        .map((issue) => {
          const path = (issue.loc ?? []).filter((part) => part !== 'body').join('.')
          return path ? `${path}: ${issue.msg ?? ''}` : (issue.msg ?? '')
        })
        .filter(Boolean)
        .join(' · ')
    }
  }
  return `El servidor respondió ${status} sin detalle.`
}

const http: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  timeout: TIMEOUTS.fast,
  headers: { 'Content-Type': 'application/json' },
})

/**
 * One place where a transport failure becomes one of two kinds of error: the
 * engine refused (`ApiError`, with the server's own sentence in it) or the
 * engine was not there (`OfflineError`, which is what the Plan B screen reads).
 * Anything else would leave the UI guessing which of the two happened.
 */
http.interceptors.response.use(
  (response) => response,
  (error: unknown) => {
    if (axios.isAxiosError(error)) {
      if (error.response) {
        throw new ApiError(
          error.response.status,
          detailOf(error.response.status, error.response.data),
        )
      }
      if (error.code === 'ECONNABORTED' || error.code === 'ETIMEDOUT') {
        throw new OfflineError(
          `La petición a ${error.config?.url ?? BASE_URL} superó el tiempo de espera.`,
        )
      }
      throw new OfflineError(
        `No se pudo contactar con el motor en ${BASE_URL}${error.config?.url ?? ''}.`,
      )
    }
    throw error
  },
)

async function get<T>(path: string, config?: AxiosRequestConfig): Promise<T> {
  return (await http.get<T>(path, config)).data
}

async function post<T>(path: string, body: unknown, timeout?: number): Promise<T> {
  return (await http.post<T>(path, body, timeout ? { timeout } : undefined)).data
}

/** Liveness probe. Deliberately not one of the five: it says nothing about a baseline. */
export async function health(): Promise<boolean> {
  try {
    await get<{ status: string }>('/health', { timeout: 4_000 })
    return true
  } catch {
    return false
  }
}

/** 1/5 — free text in, a reviewable draft out. The operator corrects it. */
export function parseAsset(body: AssetParseRequest): Promise<ParseResult> {
  return post<ParseResult>('/asset/parse', body, TIMEOUTS.parse)
}

/** 2/5 — profile in, side-by-side options per capability out. */
export function fetchCandidates(body: CandidatesRequest): Promise<CandidatesResponse> {
  // An `explain` scope puts the LLM on the path (UCM-14, P1): minutes, not
  // milliseconds. Everything else is the deterministic core plus retrieval.
  return post<CandidatesResponse>(
    '/candidates',
    body,
    body.explain ? TIMEOUTS.explain : TIMEOUTS.fast,
  )
}

/** 3/5 — the human's choices, verified against Tier 0, signed and recorded. */
export function composeBaseline(body: ComposeRequest): Promise<ComposedBaseline> {
  return post<ComposedBaseline>('/baseline/compose', body)
}

/** 4/5 — the full trail behind one baseline, plus the re-walk of its hash chain. */
export function fetchAuditLog(baselineId: string): Promise<BaselineAuditLog> {
  return get<BaselineAuditLog>(`/baseline/${baselineId}/audit-log`)
}

/**
 * 5/5 — the regional delta for one zone.
 *
 * Note what the signature cannot express: there is no inline-profile variant.
 * `GET /delta` takes a `profile_id`, so the delta is only available over a
 * profile frozen in the repository — the UI says so rather than hiding the
 * stage (`StageDelta`).
 *
 * `regions` is serialised as `US,EU` rather than repeated: the comma form is the
 * one written into the PRD and the ticket, and the route parses both.
 */
export function fetchDelta(params: {
  regions: Jurisdiction[]
  profileId: string
  zoneId: string
}): Promise<RegionalDelta> {
  return get<RegionalDelta>('/delta', {
    params: {
      regions: params.regions.join(','),
      profile_id: params.profileId,
      zone_id: params.zoneId,
    },
  })
}

/** Which of the two ways of naming a profile a request should carry. */
export function profileRef(
  profile: AssetProfile | null,
  profileId: string | null,
): { profile?: AssetProfile; profile_id?: string } {
  // Exactly one: `requested_profile` refuses both, because the engine does not
  // choose its own input (server/app/api/deps.py).
  return profile ? { profile } : { profile_id: profileId ?? undefined }
}
