/**
 * The PulseGrid live dashboard.
 *
 * One screen answers three questions, in order: is the fleet healthy (tiles +
 * API list), what is the selected API doing (latency, traffic + forecast,
 * errors), and what went wrong (endpoint table + explained alerts).
 *
 * Live data arrives over the `/v1/stream` SSE channel. Everything that depends
 * on the *selected* API is fetched on demand and refreshed whenever a frame
 * lands, so the charts stay current without the page holding a socket per panel.
 */

import { useEffect, useMemo, useState } from 'react'

import './App.css'
import {
  fetchAlerts,
  fetchEndpoints,
  fetchErrors,
  fetchForecast,
  fetchLatency,
  fetchModelMetrics,
  fetchTraffic,
} from './api'
import { ErrorChart, LatencyChart, TrafficChart } from './components/Charts'
import { AlertFeed, ApiList, EndpointTable, ModelPanel } from './components/Panels'
import { Empty, Panel, StatTile } from './components/Primitives'
import { compact, millis, percent } from './format'
import { useAsync, useLiveSnapshot, useTheme, type LiveState } from './hooks'
import { chartTokens } from './theme'

/** Selectable look-back windows, in minutes. */
const WINDOWS = [
  { label: '15m', value: 15 },
  { label: '1h', value: 60 },
  { label: '6h', value: 360 },
  { label: '24h', value: 1440 },
] as const

/** How far ahead the traffic forecast is drawn. */
const FORECAST_HORIZON_MIN = 30

/** Human-readable text for each live-connection state. */
const LIVE_LABEL: Record<LiveState, string> = {
  connecting: 'Connecting',
  live: 'Live',
  polling: 'Polling',
  offline: 'Offline',
}

/**
 * Header badge reporting how fresh the data is.
 *
 * It distinguishes streaming from polling rather than always claiming "live":
 * a dashboard that lies about its own freshness is worse than one that admits
 * it fell back.
 */
function LiveBadge({ state }: { state: LiveState }) {
  return (
    <span className={`live live--${state}`}>
      <span className="live__dot" aria-hidden="true" />
      {LIVE_LABEL[state]}
    </span>
  )
}

/** The dashboard. */
export default function App() {
  const [windowMin, setWindowMin] = useState<number>(60)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const { choice, setChoice, dark } = useTheme()
  const { snapshot, state, error, tick } = useLiveSnapshot(windowMin)

  const apis = useMemo(() => snapshot?.apis ?? [], [snapshot])
  const tokens = useMemo(() => chartTokens(dark), [dark])

  // Default to the worst-scoring API — the one an operator opened the dashboard
  // to look at — and hold that choice until it disappears from the fleet.
  useEffect(() => {
    if (!apis.length) return
    setSelectedId((current) =>
      current !== null && apis.some((api) => api.api_id === current) ? current : apis[0].api_id,
    )
  }, [apis])

  const selected = apis.find((api) => api.api_id === selectedId) ?? null
  const apiNames = useMemo(() => new Map(apis.map((api) => [api.api_id, api.name] as const)), [apis])

  const latency = useAsync(
    async (signal) =>
      selectedId === null
        ? null
        : Promise.all([
            fetchLatency(selectedId, windowMin, 'p50', signal),
            fetchLatency(selectedId, windowMin, 'p95', signal),
            fetchLatency(selectedId, windowMin, 'p99', signal),
          ]),
    [selectedId, windowMin, tick],
  )

  const traffic = useAsync(
    async (signal) => (selectedId === null ? null : fetchTraffic(selectedId, windowMin, signal)),
    [selectedId, windowMin, tick],
  )

  const forecast = useAsync(
    async (signal) =>
      selectedId === null ? null : fetchForecast(selectedId, FORECAST_HORIZON_MIN, signal),
    [selectedId, tick],
  )

  const errorSeries = useAsync(
    async (signal) => (selectedId === null ? null : fetchErrors(selectedId, windowMin, signal)),
    [selectedId, windowMin, tick],
  )

  const endpoints = useAsync(
    async (signal) => (selectedId === null ? null : fetchEndpoints(selectedId, windowMin, signal)),
    [selectedId, windowMin, tick],
  )

  const alerts = useAsync(
    async (signal) => snapshot?.alerts ?? (await fetchAlerts(windowMin, signal)),
    [windowMin, tick],
  )

  const models = useAsync(async (signal) => fetchModelMetrics(signal), [tick])

  const summary = snapshot?.summary
  const errorTone = !summary
    ? 'neutral'
    : summary.error_rate >= 5
      ? 'critical'
      : summary.error_rate > 0
        ? 'warning'
        : 'good'

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand__pulse" aria-hidden="true" />
          <h1>PulseGrid</h1>
          <span className="brand__tag">API analytics &amp; performance management</span>
        </div>

        <div className="controls">
          <LiveBadge state={state} />

          <div className="segmented" role="group" aria-label="Look-back window">
            {WINDOWS.map((option) => (
              <button
                key={option.value}
                type="button"
                className={option.value === windowMin ? 'segmented__on' : undefined}
                onClick={() => setWindowMin(option.value)}
                aria-pressed={option.value === windowMin}
              >
                {option.label}
              </button>
            ))}
          </div>

          <div className="segmented" role="group" aria-label="Colour theme">
            {(['system', 'light', 'dark'] as const).map((option) => (
              <button
                key={option}
                type="button"
                className={option === choice ? 'segmented__on' : undefined}
                onClick={() => setChoice(option)}
                aria-pressed={option === choice}
              >
                {option === 'system' ? 'Auto' : option === 'light' ? 'Light' : 'Dark'}
              </button>
            ))}
          </div>
        </div>
      </header>

      {error ? (
        <p className="banner" role="alert">
          Cannot reach the PulseGrid API ({error}). Is the backend running on port 8000?
        </p>
      ) : null}

      <section className="tiles" aria-label="Fleet summary">
        <StatTile label="APIs monitored" value={summary ? String(summary.api_count) : '—'} />
        <StatTile
          label="Requests"
          value={summary ? compact(summary.total_requests) : '—'}
          sub={`last ${windowMin} min`}
        />
        <StatTile
          label="Error rate"
          value={summary ? percent(summary.error_rate) : '—'}
          tone={errorTone}
          sub="5xx and transport failures"
        />
        <StatTile
          label="p95 latency"
          value={summary ? millis(summary.p95_ms) : '—'}
          sub="request-weighted, fleet-wide"
        />
        <StatTile
          label="Open alerts"
          value={summary ? String(summary.open_alerts) : '—'}
          tone={summary && summary.open_alerts > 0 ? 'warning' : 'good'}
          sub="still firing"
        />
      </section>

      <main className="grid">
        <Panel title="Fleet" hint="Worst health score first">
          <ApiList apis={apis} selectedId={selectedId} onSelect={setSelectedId} />
        </Panel>

        <Panel
          title="Latency percentiles"
          hint={selected ? `${selected.name} · p50 / p95 / p99` : 'Select an API'}
        >
          {selected && latency.data ? (
            <LatencyChart
              p50={latency.data[0].points}
              p95={latency.data[1].points}
              p99={latency.data[2].points}
              sloMs={selected.slo_latency_ms}
              tokens={tokens}
            />
          ) : (
            <Empty message={latency.loading ? 'Loading…' : 'No API selected.'} />
          )}
        </Panel>

        <Panel
          title="Traffic and forecast"
          hint={`Requests per minute, with the next ${FORECAST_HORIZON_MIN} minutes predicted`}
        >
          {selected && traffic.data ? (
            <TrafficChart
              traffic={traffic.data.points}
              forecast={forecast.data?.points ?? []}
              forecastFrom={forecast.data?.generated_at ?? null}
              tokens={tokens}
            />
          ) : (
            <Empty message={traffic.loading ? 'Loading…' : 'No API selected.'} />
          )}
        </Panel>

        <Panel
          title="Error rate"
          hint={selected ? `Against a ${percent((1 - selected.slo_target) * 100, 1)} budget` : ''}
        >
          {selected && errorSeries.data ? (
            <ErrorChart
              errors={errorSeries.data.points}
              sloTarget={selected.slo_target}
              tokens={tokens}
            />
          ) : (
            <Empty message={errorSeries.loading ? 'Loading…' : 'No API selected.'} />
          )}
        </Panel>

        <Panel title="Endpoints" hint="Slowest first" wide>
          <EndpointTable
            endpoints={endpoints.data?.endpoints ?? []}
            sloMs={selected?.slo_latency_ms ?? 0}
          />
        </Panel>

        <Panel title="Detected anomalies" hint="Robust z-score and IsolationForest, with reasons">
          <AlertFeed alerts={alerts.data ?? []} apiNames={apiNames} />
        </Panel>

        <Panel title="Model metrics" hint="Last refit, against the seasonal-naive baseline">
          <ModelPanel metrics={models.data ?? []} />
        </Panel>
      </main>

      <footer className="foot">
        <span>
          Collected through the reverse proxy, <code>/v1/ingest</code> and an active prober.
          Analytics read only from <code>metric_rollup</code>.
        </span>
        <a href="/docs">API docs</a>
      </footer>
    </div>
  )
}
