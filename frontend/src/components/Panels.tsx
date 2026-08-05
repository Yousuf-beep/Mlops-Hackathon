/**
 * The dashboard's tabular and list panels.
 */

import { compact, millis, percent, since } from '../format'
import { describeApi, read, type ReadingMode } from '../narrate'
import { STATUS_COLOR } from '../theme'
import type { Alert, ApiOverviewItem, EndpointBreakdownItem, ModelMetrics } from '../types'
import { Empty, SeverityBadge, StatusBadge } from './Primitives'

/** Pick a string for the reading mode in force. */
function say(mode: ReadingMode, plain: string, engineer: string): string {
  return mode === 'plain' ? plain : engineer
}

/** One row of a {@link RankedBarList}. */
interface RankedRow {
  key: string
  label: string
  value: number
  display: string
}

/** Props for {@link RankedBarList}. */
interface RankedBarListProps {
  rows: RankedRow[]
  tone: 'accent' | 'warning' | 'critical'
  emptyMessage: string
}

/**
 * A horizontal bar-per-row ranked list — the shared shape behind "top slow
 * endpoints", "top failing endpoints" and "traffic distribution". A sorted
 * bar list reads magnitude *and* rank at once, which a pie chart does not,
 * and stays on one axis (share of the row's own max) rather than mixing scales.
 */
function RankedBarList({ rows, tone, emptyMessage }: RankedBarListProps) {
  if (!rows.length) return <Empty message={emptyMessage} />
  const max = Math.max(1, ...rows.map((row) => row.value))
  return (
    <ul className="ranklist">
      {rows.map((row) => (
        <li key={row.key}>
          <div className="ranklist__row">
            <code>{row.label}</code>
            <span>{row.display}</span>
          </div>
          <div className="ranklist__track">
            <div
              className={`ranklist__fill ranklist__fill--${tone}`}
              style={{ width: `${(row.value / max) * 100}%` }}
            />
          </div>
        </li>
      ))}
    </ul>
  )
}

/** Props for {@link TopSlowEndpoints} and {@link TopFailingEndpoints}. */
export interface EndpointRankingProps {
  endpoints: EndpointBreakdownItem[]
  limit?: number
}

/** The endpoints dragging p95 latency up the most, worst first. */
export function TopSlowEndpoints({ endpoints, limit = 6 }: EndpointRankingProps) {
  const rows = [...endpoints]
    .sort((a, b) => b.p95_ms - a.p95_ms)
    .slice(0, limit)
    .map((row) => ({ key: row.endpoint, label: row.endpoint, value: row.p95_ms, display: millis(row.p95_ms) }))
  return (
    <RankedBarList rows={rows} tone="warning" emptyMessage="No endpoint activity in this window yet." />
  )
}

/** The endpoints with the highest error rate, worst first. */
export function TopFailingEndpoints({ endpoints, limit = 6 }: EndpointRankingProps) {
  const rows = [...endpoints]
    .filter((row) => row.error_rate > 0)
    .sort((a, b) => b.error_rate - a.error_rate)
    .slice(0, limit)
    .map((row) => ({
      key: row.endpoint,
      label: row.endpoint,
      value: row.error_rate,
      display: percent(row.error_rate, 1),
    }))
  return (
    <RankedBarList rows={rows} tone="critical" emptyMessage="No errors in this window. Nothing to rank." />
  )
}

/** Share of total requests each endpoint accounts for, busiest first. */
export function TrafficDistribution({ endpoints, limit = 8 }: EndpointRankingProps) {
  const total = endpoints.reduce((sum, row) => sum + row.req_count, 0)
  const rows = [...endpoints]
    .sort((a, b) => b.req_count - a.req_count)
    .slice(0, limit)
    .map((row) => ({
      key: row.endpoint,
      label: row.endpoint,
      value: row.req_count,
      display: `${percent(total ? (100 * row.req_count) / total : 0, 1)} · ${compact(row.req_count)} req`,
    }))
  return (
    <RankedBarList rows={rows} tone="accent" emptyMessage="No traffic recorded in this window yet." />
  )
}

/** Props for {@link ApiList}. */
export interface ApiListProps {
  apis: ApiOverviewItem[]
  selectedId: number | null
  onSelect: (apiId: number) => void
  mode: ReadingMode
}

/**
 * The fleet, worst score first — the order an operator triages in.
 *
 * Each row says what is wrong with its API in a sentence before it shows the
 * numbers behind that judgement, so the first row is always both the thing to
 * fix and the reason it needs fixing. The status colour is repeated as a bar
 * down the leading edge, which is what makes the shape of the list readable
 * from across a room; it never carries the state on its own, because the badge
 * and the sentence are already saying it.
 *
 * Doubles as the dashboard's table view: every number the charts encode with
 * colour is also readable here as text.
 */
export function ApiList({ apis, selectedId, onSelect, mode }: ApiListProps) {
  if (!apis.length) {
    return <Empty message="No APIs registered yet. POST one to /v1/apis to start monitoring." />
  }

  return (
    <ul className="apilist">
      {apis.map((api) => (
        <li key={api.api_id}>
          <button
            type="button"
            className={`apirow apirow--${api.status}${api.api_id === selectedId ? ' apirow--on' : ''}`}
            onClick={() => onSelect(api.api_id)}
            aria-pressed={api.api_id === selectedId}
          >
            <span className="apirow__top">
              <span className="apirow__name">{api.name}</span>
              <StatusBadge status={api.status} />
            </span>
            <span className="apirow__say">{read(mode, describeApi(api))}</span>
            <span className="apirow__meta">
              <span>
                score <strong style={{ color: STATUS_COLOR[api.status] }}>{api.score}</strong>
              </span>
              <span>p95 {millis(api.p95_ms)}</span>
              <span>err {percent(api.error_rate, 1)}</span>
              <span>{compact(api.req_count)} req</span>
              {api.open_alerts > 0 ? (
                <span className="apirow__alerts">
                  {api.open_alerts} {say(mode, 'unexplained', 'open')}
                </span>
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
  mode: ReadingMode
}

/**
 * Per-endpoint Golden Signals, slowest first.
 *
 * Percentile columns use tabular figures so the digits line up down the column
 * and an outlier is visible without reading a single number. In plain mode the
 * headers name the reader the percentile describes rather than the percentile
 * itself — the column is the same column either way, but "worst 1 in 100" is
 * legible to the whole room and "p99" is not.
 */
export function EndpointTable({ endpoints, sloMs, mode }: EndpointTableProps) {
  if (!endpoints.length) return <Empty message="No endpoint activity in this window yet." />

  return (
    <div className="tablewrap">
      <table className="table">
        <thead>
          <tr>
            <th scope="col">Endpoint</th>
            <th scope="col">Requests</th>
            <th scope="col">{say(mode, 'Failed', 'Errors')}</th>
            <th scope="col">{say(mode, 'Typical', 'p50')}</th>
            <th scope="col">{say(mode, 'Slow 1 in 20', 'p95')}</th>
            <th scope="col">{say(mode, 'Worst 1 in 100', 'p99')}</th>
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
  mode: ReadingMode
}

/**
 * Detected incidents, newest first.
 *
 * Each row leads with the detector's own explanation rather than the raw score:
 * "why did this fire?" is the question an alert has to answer. Confidence is a
 * secondary line, not the headline — it is a heuristic on top of the severity
 * bucket, not a replacement for it.
 */
export function AlertFeed({ alerts, mode }: AlertFeedProps) {
  if (!alerts.length) {
    return (
      <p className="allclear">
        {say(
          mode,
          'Nothing looks unusual. Every service is behaving the way it normally does.',
          'No anomalies detected in this window.',
        )}
      </p>
    )
  }

  return (
    <ul className="alerts">
      {alerts.map((alert) => (
        <li key={alert.id} className={alert.resolved_at ? 'alert alert--closed' : 'alert'}>
          <div className="alert__head">
            <SeverityBadge severity={alert.severity} />
            <span className="alert__api">{alert.api_name}</span>
            <span className="alert__when">
              {alert.resolved_at ? 'resolved' : since(alert.fired_at)}
            </span>
          </div>
          <p className="alert__why">
            {alert.explanation}{' '}
            <strong className="alert__state">
              {alert.resolved_at
                ? say(mode, 'Over — no action needed.', 'Resolved.')
                : say(mode, 'Still happening.', 'Firing.')}
            </strong>
          </p>
          <p className="alert__band">
            {say(mode, 'measured', 'observed')} {alert.metric_value} ·{' '}
            {say(mode, 'normal range', 'expected')} {alert.expected_range}
            {alert.confidence != null ? ` · ${percent(alert.confidence * 100, 0)} confidence` : ''}
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
export function ModelPanel({ metrics, mode }: { metrics: ModelMetrics[]; mode: ReadingMode }) {
  if (!metrics.length) {
    return <Empty message="No refit has run yet. Metrics appear after the first forecast job." />
  }

  return (
    <div className="tablewrap">
      <table className="table">
        <thead>
          <tr>
            <th scope="col">{say(mode, 'Method', 'Model')}</th>
            <th scope="col">{say(mode, 'Typical miss', 'MAE')}</th>
            <th scope="col">RMSE</th>
            <th scope="col">{say(mode, '% off', 'MAPE')}</th>
            <th scope="col">{say(mode, 'Updated', 'Fitted')}</th>
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
