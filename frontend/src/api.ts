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
  EndpointBreakdownResponse,
  ForecastResponse,
  HealthTimelineResponse,
  HeatmapResponse,
  ModelMetrics,
  Snapshot,
  TimeseriesResponse,
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
 * Fetch JSON from the API, raising {@link ApiError} on a non-2xx response.
 *
 * @param path Path beginning with `/`, e.g. `/v1/analytics/summary`.
 * @param signal Abort signal so a stale request is dropped when the user
 *   switches API or window before it lands.
 * @returns The parsed response body.
 */
async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    signal,
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) {
    throw new ApiError(response.status, `${path} responded ${response.status}`)
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
