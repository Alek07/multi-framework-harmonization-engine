/**
 * The declared endpoints, and nothing else (`SURFACE`, server/app/api/router.py).
 *
 * Every call returns the server's own shape untouched: nothing here merges,
 * filters or reorders a response.
 */

import axios, { type AxiosInstance, type AxiosRequestConfig } from 'axios'

import type {
  AssetParseRequest,
  AssetProfile,
  BaselineAuditLog,
  BaselineList,
  BaselineStatement,
  CandidatesRequest,
  CandidatesResponse,
  ComposeRequest,
  ComposedBaseline,
  DeltaMode,
  DeltaRegime,
  Jurisdiction,
  ParseResult,
  RegionalDelta,
} from './types'

/** `/api/v1` on this origin by default; the dev server proxies it (vite.config.ts). */
const BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

/**
 * Timeouts sized by what the call actually does on the reference machine.
 *
 * `fast` is for the calls that are pure arithmetic over the versioned catalog —
 * composing, reading a trail, the regional delta — which answer in
 * milliseconds.
 *
 * `candidates` is not one of them, and the reason is measured rather than
 * guessed: the *first* run of a freshly started backend has to load the
 * ~1.1 GB embedding model before its first retrieval query, which took over a
 * minute here and made the UI give up on a request the engine was still
 * honouring. Every later run answers in seconds. The screen says what is
 * happening while it waits, and the request is retryable — but the client has
 * no business being less patient than the process it is talking to.
 *
 * `parse` is measured too: 77 s with the weights in memory, 262 s with them only
 * on disk, same answer. The stack preloads at startup, so the cold path is rare
 * rather than impossible — 420 s covers it with room for a slower machine.
 *
 * One explanation batch is ~12 paragraphs of the same model, which is why the
 * server gives that path its own 600 s budget (`EXPLAIN_TIMEOUT_SECONDS`).
 */
const TIMEOUTS = {
  fast: 60_000,
  candidates: 300_000,
  parse: 420_000,
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
  return `El sistema ha rechazado la petición (código ${status}) sin dar más detalle.`
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
          'El sistema ha tardado más de lo previsto en responder. Vuelve a intentarlo: el ' +
            'primer análisis después de arrancar el sistema carga el modelo en memoria y es ' +
            'bastante más lento que los siguientes, así que el segundo intento suele bastar.',
        )
      }
      throw new OfflineError(
        'No se ha podido contactar con el sistema. Comprueba que esté arrancado y vuelve a ' +
          'intentarlo: no se pierde nada de lo que llevas hecho.',
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
    body.explain ? TIMEOUTS.explain : TIMEOUTS.candidates,
  )
}

/** 3/5 — the human's choices, verified against Tier 0, signed and recorded. */
export function composeBaseline(body: ComposeRequest): Promise<ComposedBaseline> {
  return post<ComposedBaseline>('/baseline/compose', body)
}

/** 6/7 — every baseline signed in this ledger, newest first (UCM-21). */
export function fetchBaselines(): Promise<BaselineList> {
  return get<BaselineList>('/baselines')
}

/** 7/7 — the signed baseline as a declaration of applicability (UCM-46). */
export function fetchStatement(baselineId: string): Promise<BaselineStatement> {
  return get<BaselineStatement>(`/baseline/${baselineId}/statement`)
}

/**
 * The same declaration in NIST's vocabulary: a partial OSCAL system-security-plan.
 *
 * Typed as `unknown` and not modelled here on purpose. It is a foreign schema
 * that this client only ever hands to the operator as a file — mirroring it in
 * TypeScript would create a second definition of OSCAL that could drift from the
 * server's without anything failing.
 */
export function fetchOscalStatement(baselineId: string): Promise<unknown> {
  return get<unknown>(`/baseline/${baselineId}/statement`, { params: { format: 'oscal' } })
}

/** 4/5 — the full trail behind one baseline, plus the re-walk of its hash chain. */
export function fetchAuditLog(baselineId: string): Promise<BaselineAuditLog> {
  return get<BaselineAuditLog>(`/baseline/${baselineId}/audit-log`)
}

/**
 * 5/5 — the regional delta for one zone of the asset being composed.
 *
 * It carries the reviewed profile inline, exactly like `/candidates` and
 * `/baseline/compose`. That is the whole point of the endpoint taking a body:
 * the asset the operator described and composed has no id in the repository, and
 * "what changes if I also answer to EU obligations" is the same question for it
 * as for a frozen profile.
 */
export function fetchDelta(body: {
  regions: Jurisdiction[]
  profile?: AssetProfile | null
  profileId?: string | null
  zoneId: string
  mode?: DeltaMode
  regime?: DeltaRegime
}): Promise<RegionalDelta> {
  return post<RegionalDelta>('/delta', {
    regions: body.regions,
    ...profileRef(body.profile ?? null, body.profileId ?? null),
    zone_id: body.zoneId,
    ...(body.mode ? { mode: body.mode } : {}),
    ...(body.regime ? { regime: body.regime } : {}),
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
