/**
 * The dashboard's tabular and list panels.
 */

import { compact, millis, percent, since } from '../format'
import { STATUS_COLOR } from '../theme'
import type { Alert, ApiOverviewItem, EndpointBreakdownItem, ModelMetrics } from '../types'
import { Empty, SeverityBadge, StatusBadge } from './Primitives'

/** Props for {@link ApiList}. */
export interface ApiListProps {
  apis: ApiOverviewItem[]
  selectedId: number | null
  onSelect: (apiId: number) => void
}

/**
 * The fleet, worst score first — the order an operator triages in.
 *
 * Doubles as the dashboard's table view: every number the charts encode with
 * colour is also readable here as text.
 */
export function ApiList({ apis, selectedId, onSelect }: ApiListProps) {
  if (!apis.length) {
    return <Empty message="No APIs registered yet. POST one to /v1/apis to start monitoring." />
  }

  return (
    <ul className="apilist">
      {apis.map((api) => (
        <li key={api.api_id}>
          <button
            type="button"
            className={api.api_id === selectedId ? 'apirow apirow--on' : 'apirow'}
            onClick={() => onSelect(api.api_id)}
            aria-pressed={api.api_id === selectedId}
          >
            <span className="apirow__top">
              <span className="apirow__name">{api.name}</span>
              <StatusBadge status={api.status} />
            </span>
            <span className="apirow__meta">
              <span>
                score <strong style={{ color: STATUS_COLOR[api.status] }}>{api.score}</strong>
              </span>
              <span>p95 {millis(api.p95_ms)}</span>
              <span>err {percent(api.error_rate, 1)}</span>
              <span>{compact(api.req_count)} req</span>
              {api.open_alerts > 0 ? (
                <span className="apirow__alerts">{api.open_alerts} open</span>
              ) : null}
            </span>
          </button>
        </li>
      ))}
    </ul>
  )
}

/** Props for {@link EndpointTable}. */
export interface EndpointTableProps {
  endpoints: EndpointBreakdownItem[]
  sloMs: number
}

/**
 * Per-endpoint Golden Signals, slowest first.
 *
 * Percentile columns use tabular figures so the digits line up down the column
 * and an outlier is visible without reading a single number.
 */
export function EndpointTable({ endpoints, sloMs }: EndpointTableProps) {
  if (!endpoints.length) return <Empty message="No endpoint activity in this window yet." />

  return (
    <div className="tablewrap">
      <table className="table">
        <thead>
          <tr>
            <th scope="col">Endpoint</th>
            <th scope="col">Requests</th>
            <th scope="col">Errors</th>
            <th scope="col">p50</th>
            <th scope="col">p95</th>
            <th scope="col">p99</th>
          </tr>
        </thead>
        <tbody>
          {endpoints.map((row) => (
            <tr key={row.endpoint}>
              <th scope="row">
                <code>{row.endpoint}</code>
              </th>
              <td>{compact(row.req_count)}</td>
              <td className={row.error_rate > 0 ? 'cell--bad' : undefined}>
                {percent(row.error_rate, 1)}
              </td>
              <td>{millis(row.p50_ms)}</td>
              <td className={row.p95_ms > sloMs ? 'cell--bad' : undefined}>{millis(row.p95_ms)}</td>
              <td>{millis(row.p99_ms)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** Props for {@link AlertFeed}. */
export interface AlertFeedProps {
  alerts: Alert[]
  apiNames: Map<number, string>
}

/**
 * Detected incidents, newest first.
 *
 * Each row leads with the detector's own explanation rather than the raw score:
 * "why did this fire?" is the question an alert has to answer.
 */
export function AlertFeed({ alerts, apiNames }: AlertFeedProps) {
  if (!alerts.length) {
    return <Empty message="No anomalies detected. The detectors need ~10 minutes of history." />
  }

  return (
    <ul className="alerts">
      {alerts.map((alert) => (
        <li key={alert.id} className={alert.resolved_at ? 'alert alert--closed' : 'alert'}>
          <div className="alert__head">
            <SeverityBadge severity={alert.severity} />
            <span className="alert__api">{apiNames.get(alert.api_id) ?? `API ${alert.api_id}`}</span>
            <span className="alert__when">
              {alert.resolved_at ? 'resolved' : since(alert.fired_at)}
            </span>
          </div>
          <p className="alert__why">{alert.explanation}</p>
          <p className="alert__band">
            observed {alert.metric_value} · expected {alert.expected_range}
          </p>
        </li>
      ))}
    </ul>
  )
}

/**
 * Model-evaluation metrics from the most recent refit.
 *
 * Showing the seasonal-naive baseline beside the model is the point: a forecast
 * that cannot beat "same as last time" is not worth deploying, and this panel
 * is where that claim is checkable.
 */
export function ModelPanel({ metrics }: { metrics: ModelMetrics[] }) {
  if (!metrics.length) {
    return <Empty message="No refit has run yet. Metrics appear after the first forecast job." />
  }

  return (
    <div className="tablewrap">
      <table className="table">
        <thead>
          <tr>
            <th scope="col">Model</th>
            <th scope="col">MAE</th>
            <th scope="col">RMSE</th>
            <th scope="col">MAPE</th>
            <th scope="col">Fitted</th>
          </tr>
        </thead>
        <tbody>
          {metrics.map((entry) => (
            <tr key={entry.model_name}>
              <th scope="row">
                <code>{entry.model_name}</code>
              </th>
              <td>{entry.mae?.toFixed(2) ?? '—'}</td>
              <td>{entry.rmse?.toFixed(2) ?? '—'}</td>
              <td>{entry.mape != null ? percent(entry.mape, 1) : '—'}</td>
              <td>{since(entry.trained_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
