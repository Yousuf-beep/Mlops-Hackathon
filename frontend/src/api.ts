/**
 * Typed access to the PulseGrid API.
 *
 * Requests go to a relative path by default so Vite's dev proxy (and, in
 * production, whatever serves the built assets) forwards them to the backend on
 * the same origin — which keeps CORS out of the picture entirely. Point
 * `VITE_API_BASE` at an absolute URL to talk to a backend elsewhere.
 */

import type {
  Alert,
  ApiCreatePayload,
  ApiRead,
  EndpointBreakdownResponse,
  ForecastResponse,
  HealthTimelineResponse,
  HeatmapResponse,
  ModelMetrics,
  Snapshot,
  TimeseriesResponse,
  Token,
  UserRead,
} from './types'

/** Base URL every request is resolved against. Empty means same-origin. */
export const API_BASE: string = import.meta.env.VITE_API_BASE ?? ''

/** An API call that came back with a non-2xx status. */
export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/**
 * Extract the `{"detail": "..."}` message FastAPI puts on every error
 * response, falling back to a generic message when the body isn't that shape
 * (a network failure, an HTML error page from a proxy in front of the API).
 */
async function errorDetail(response: Response, path: string): Promise<string> {
  try {
    const body: unknown = await response.clone().json()
    if (body && typeof body === 'object' && 'detail' in body) {
      const detail = (body as { detail: unknown }).detail
      if (typeof detail === 'string') return detail
    }
  } catch {
    // not JSON — fall through to the generic message
  }
  return `${path} responded ${response.status}`
}

/**
 * Fetch JSON from the API, raising {@link ApiError} on a non-2xx response.
 *
 * @param path Path beginning with `/`, e.g. `/v1/analytics/summary`.
 * @param signal Abort signal so a stale request is dropped when the user
 *   switches API or window before it lands.
 * @param token Bearer token for routes that require authentication.
 * @returns The parsed response body.
 */
async function getJson<T>(path: string, signal?: AbortSignal, token?: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    signal,
    headers: {
      Accept: 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  })
  if (!response.ok) {
    throw new ApiError(response.status, await errorDetail(response, path))
  }
  return (await response.json()) as T
}

/**
 * POST a JSON body to the API, raising {@link ApiError} on a non-2xx response.
 *
 * @param path Path beginning with `/`.
 * @param body Request payload, JSON-serialised.
 * @param token Bearer token for routes that require authentication.
 * @returns The parsed response body.
 */
async function postJson<T>(path: string, body: unknown, token?: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    throw new ApiError(response.status, await errorDetail(response, path))
  }
  return (await response.json()) as T
}

/** URL of the Server-Sent Events stream. */
export function streamUrl(windowMin: number): string {
  return `${API_BASE}/v1/stream?window_min=${windowMin}`
}

/** Fetch the fleet overview — the same payload the SSE `snapshot` frame carries. */
export function fetchOverview(windowMin: number, signal?: AbortSignal): Promise<Snapshot> {
  return getJson<Snapshot>(`/v1/analytics/overview?window_min=${windowMin}`, signal)
}

/** Appends `&since=` when supplied, for an incremental (append-only) fetch. */
function sinceParam(since?: string): string {
  return since ? `&since=${encodeURIComponent(since)}` : ''
}

/**
 * Fetch a latency percentile series for one API.
 *
 * @param since When supplied, restricts the response to points at or after
 *   the second-to-last point the caller already holds — the live-updating
 *   "current minute" bucket is intentionally re-sent so a chart merging by
 *   bucket picks up its revisions instead of freezing until it closes.
 */
export function fetchLatency(
  apiId: number,
  windowMin: number,
  percentile: 'p50' | 'p95' | 'p99' | 'avg',
  signal?: AbortSignal,
  since?: string,
): Promise<TimeseriesResponse> {
  return getJson<TimeseriesResponse>(
    `/v1/analytics/latency?api_id=${apiId}&window_min=${windowMin}&percentile=${percentile}${sinceParam(since)}`,
    signal,
  )
}

/** Fetch the requests-per-minute series for one API. See {@link fetchLatency} re: `since`. */
export function fetchTraffic(
  apiId: number,
  windowMin: number,
  signal?: AbortSignal,
  since?: string,
): Promise<TimeseriesResponse> {
  return getJson<TimeseriesResponse>(
    `/v1/analytics/traffic?api_id=${apiId}&window_min=${windowMin}${sinceParam(since)}`,
    signal,
  )
}

/** Fetch the error-rate series for one API. See {@link fetchLatency} re: `since`. */
export function fetchErrors(
  apiId: number,
  windowMin: number,
  signal?: AbortSignal,
  since?: string,
): Promise<TimeseriesResponse> {
  return getJson<TimeseriesResponse>(
    `/v1/analytics/errors?api_id=${apiId}&window_min=${windowMin}${sinceParam(since)}`,
    signal,
  )
}

/** Fetch one API's health-score history, for the up/down timeline panel. */
export function fetchHealthTimeline(
  apiId: number,
  windowMin: number,
  signal?: AbortSignal,
): Promise<HealthTimelineResponse> {
  return getJson<HealthTimelineResponse>(
    `/v1/analytics/health-timeline?api_id=${apiId}&window_min=${windowMin}`,
    signal,
  )
}

/** Fetch the (time x endpoint) request-volume heatmap for one API. */
export function fetchHeatmap(
  apiId: number,
  windowMin: number,
  signal?: AbortSignal,
): Promise<HeatmapResponse> {
  return getJson<HeatmapResponse>(
    `/v1/analytics/heatmap?api_id=${apiId}&window_min=${windowMin}`,
    signal,
  )
}

/** Fetch the per-endpoint breakdown for one API. */
export function fetchEndpoints(
  apiId: number,
  windowMin: number,
  signal?: AbortSignal,
): Promise<EndpointBreakdownResponse> {
  return getJson<EndpointBreakdownResponse>(
    `/v1/analytics/endpoints?api_id=${apiId}&window_min=${windowMin}`,
    signal,
  )
}

/** Fetch the traffic forecast for one API. */
export function fetchForecast(
  apiId: number,
  horizonMin: number,
  signal?: AbortSignal,
): Promise<ForecastResponse> {
  return getJson<ForecastResponse>(`/v1/forecast/${apiId}?horizon_min=${horizonMin}`, signal)
}

/** Fetch the fleet-wide alert feed. */
export function fetchAlerts(windowMin: number, signal?: AbortSignal): Promise<Alert[]> {
  return getJson<Alert[]>(`/v1/alerts?window_min=${windowMin}&limit=50`, signal)
}

/** Fetch the latest model-evaluation metrics. */
export function fetchModelMetrics(signal?: AbortSignal): Promise<ModelMetrics[]> {
  return getJson<ModelMetrics[]>('/v1/models/metrics', signal)
}

/**
 * Create an operator account. Always registers as `viewer` — the signup form
 * has no business minting admins, and the backend defaults to `viewer` when
 * the field is omitted anyway.
 */
export function registerUser(email: string, password: string): Promise<UserRead> {
  return postJson<UserRead>('/v1/auth/register', { email, password })
}

/** Exchange credentials for a bearer token. */
export function login(email: string, password: string): Promise<Token> {
  return postJson<Token>('/v1/auth/login', { email, password })
}

/** Fetch the account attached to a bearer token. */
export function fetchMe(token: string, signal?: AbortSignal): Promise<UserRead> {
  return getJson<UserRead>('/v1/auth/me', signal, token)
}

/** Register a new API for monitoring. Requires an authenticated caller. */
export function createApi(payload: ApiCreatePayload, token: string): Promise<ApiRead> {
  return postJson<ApiRead>('/v1/apis', payload, token)
}
