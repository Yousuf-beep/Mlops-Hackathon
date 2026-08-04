/**
 * Wire types mirroring the PulseGrid backend's Pydantic schemas.
 *
 * Hand-written rather than generated from `/openapi.json`: the surface the
 * dashboard consumes is small and stable, and a build-time codegen step would
 * make the frontend unbuildable whenever the API happens to be down.
 */

/** One minute bucket of a Golden-Signal series. */
export interface TimeseriesPoint {
  bucket: string
  value: number
}

/** A named series over a window, as returned by `/v1/analytics/*`. */
export interface TimeseriesResponse {
  api_id: number
  endpoint: string | null
  metric: string
  points: TimeseriesPoint[]
}

/** Traffic-light status derived from an API's composite health score. */
export type ApiStatus = 'healthy' | 'degraded' | 'critical' | 'no_data'

/** One row of the fleet overview. */
export interface ApiOverviewItem {
  api_id: number
  name: string
  score: number
  availability: number
  error_rate: number
  p95_ms: number
  req_count: number
  slo_target: number
  slo_latency_ms: number
  open_alerts: number
  status: ApiStatus
}

/** Fleet-wide header tiles. */
export interface Summary {
  api_count: number
  total_requests: number
  error_rate: number
  p95_ms: number
  open_alerts: number
}

/** Payload of a `snapshot` SSE frame, and of `/v1/analytics/overview`. */
export interface Snapshot {
  window_min: number
  generated_at: string
  summary: Summary
  apis: ApiOverviewItem[]
  alerts?: Alert[]
  seq?: number
}

/** Severity grades an alert can carry. */
export type AlertSeverity = 'info' | 'warning' | 'critical'

/** A fired alert with the explanation that justifies it. */
export interface Alert {
  id: number
  api_id: number
  api_name: string
  endpoint: string | null
  type: string
  severity: AlertSeverity
  signal: string
  explanation: string
  metric_value: number
  expected_range: string
  /** 0-1 heuristic confidence from the detector that fired. */
  confidence: number | null
  fired_at: string
  resolved_at: string | null
}

/** One forecast point with its 95% prediction interval. */
export interface ForecastPoint {
  horizon_min: number
  yhat: number
  yhat_lower: number
  yhat_upper: number
}

/** A traffic forecast for one API. */
export interface ForecastResponse {
  api_id: number
  generated_at: string
  points: ForecastPoint[]
}

/** Per-endpoint Golden Signals for one API. */
export interface EndpointBreakdownItem {
  endpoint: string
  req_count: number
  err_count: number
  error_rate: number
  p50_ms: number
  p95_ms: number
  p99_ms: number
  avg_ms: number
}

/** The endpoint table for one API. */
export interface EndpointBreakdownResponse {
  api_id: number
  window_min: number
  endpoints: EndpointBreakdownItem[]
}

/** One minute bucket of an API's composite health score. */
export interface HealthTimelinePoint {
  bucket: string
  score: number
  req_count: number
}

/** An API's health-score history, for the up/down timeline panel. */
export interface HealthTimelineResponse {
  api_id: number
  window_min: number
  points: HealthTimelinePoint[]
}

/** One (time bucket, endpoint) cell of the request-volume heatmap. */
export interface HeatmapCell {
  bucket: string
  endpoint: string
  req_count: number
}

/** Request-volume heatmap for one API, restricted to its busiest endpoints. */
export interface HeatmapResponse {
  api_id: number
  window_min: number
  cells: HeatmapCell[]
}

/** Role granted to a PulseGrid operator account. */
export type UserRole = 'admin' | 'viewer'

/** Public projection of an operator account, as returned by auth endpoints. */
export interface UserRead {
  id: number
  email: string
  role: UserRole
  created_at: string
}

/** Bearer token envelope returned by `POST /v1/auth/login`. */
export interface Token {
  access_token: string
  token_type: string
  expires_in: number
}

/** A registered API, as returned by `/v1/apis`. */
export interface ApiRead {
  id: number
  name: string
  base_url: string
  upstream_url: string
  owner_user_id: number
  auth_type: string | null
  slo_target: number
  slo_latency_ms: number
  created_at: string
}

/** Payload for `POST /v1/apis`. */
export interface ApiCreatePayload {
  name: string
  base_url: string
  upstream_url: string
  auth_type?: string | null
  slo_target?: number
  slo_latency_ms?: number
}

/** Offline evaluation metrics for one deployed model. */
export interface ModelMetrics {
  model_name: string
  trained_at: string
  mae: number | null
  rmse: number | null
  mape: number | null
  precision: number | null
  recall: number | null
}
