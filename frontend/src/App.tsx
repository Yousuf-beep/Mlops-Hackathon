/**
 * The PulseGrid live dashboard.
 *
 * The page is organised as an argument, not as a grid of plots. It opens with a
 * verdict — one sentence saying whether anything is wrong and what is about to
 * happen — then five answers to the questions an operator actually arrives
 * with, then the evidence behind them in a bento of panels sized by how much
 * each one matters during triage.
 *
 * Two decisions carry most of the readability:
 *
 * * **Reading mode.** Every title, legend, axis note and table header exists in
 *   a plain-English form and an instrument form. Plain is the default because
 *   this screen is read by people who did not write the service; engineer mode
 *   is one click away and never hides a number.
 * * **Sentences beside charts.** Each panel carries a lede saying what it plots
 *   with this window's real numbers in it, and a readout saying what its
 *   current shape means. Both are computed in `narrate.ts` from the same series
 *   the chart draws, so neither can drift away from what is on screen.
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
  fetchHealthTimeline,
  fetchHeatmap,
  fetchInfra,
  fetchLatency,
  fetchModelMetrics,
  fetchTraffic,
} from './api'
import {
  ErrorChart,
  HealthTimelineChart,
  HeatmapChart,
  LatencyChart,
  TrafficChart,
} from './components/Charts'
import { RegisterApiForm, SignInForm } from './components/AuthForms'
import { ContainerTable, WebEnvironments } from './components/Infra'
import {
  AlertFeed,
  ApiList,
  EndpointTable,
  ModelPanel,
  TopFailingEndpoints,
  TopSlowEndpoints,
  TrafficDistribution,
} from './components/Panels'
import { Empty, Modal, Panel, SlaGauge, StatTile } from './components/Primitives'
import { compact, millis, percent } from './format'
import {
  alertsSub,
  errorStory,
  errorSub,
  fleetDetail,
  fleetVerdict,
  healthStory,
  latencyStory,
  latencySub,
  modelStory,
  read,
  requestsSub,
  trafficOutlook,
  trafficStory,
  type Phrase,
  type ReadingMode,
} from './narrate'
import { useAuth } from './session'
import {
  useAsync,
  useIncrementalSeries,
  useLiveSnapshot,
  useReadingMode,
  useTheme,
  type LiveState,
} from './hooks'
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

/**
 * A labelled group of chips.
 *
 * The label is not decoration: three unlabelled chip groups in a row is a
 * puzzle, and the window a dashboard is showing is one of the things a reader
 * most often gets wrong about it.
 */
function Segmented<T extends string | number>({
  label,
  options,
  value,
  onChange,
}: {
  label: string
  options: readonly { label: string; value: T }[]
  value: T
  onChange: (next: T) => void
}) {
  return (
    <div className="control">
      <span className="control__label" id={`seg-${label}`}>
        {label}
      </span>
      <div className="segmented" role="group" aria-labelledby={`seg-${label}`}>
        {options.map((option) => (
          <button
            key={String(option.value)}
            type="button"
            className={option.value === value ? 'segmented__on' : undefined}
            onClick={() => onChange(option.value)}
            aria-pressed={option.value === value}
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  )
}

/** The dashboard. */
export default function App() {
  const [windowMin, setWindowMin] = useState<number>(60)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const { choice, setChoice, dark } = useTheme()
  const { mode, setMode } = useReadingMode()
  const { snapshot, state, error, tick } = useLiveSnapshot(windowMin)
  const auth = useAuth()
  const [openModal, setOpenModal] = useState<'signin' | 'register-api' | null>(null)

  const apis = useMemo(() => snapshot?.apis ?? [], [snapshot])
  const tokens = useMemo(() => chartTokens(dark), [dark])

  /** Resolve a two-register phrase for the mode currently in force. */
  const R = (value: Phrase) => read(mode, value)
  /** Resolve a pair of literals the same way. */
  const say = (plain: string, engineer: string) => (mode === 'plain' ? plain : engineer)

  // Default to the worst-scoring API — the one an operator opened the dashboard
  // to look at — and hold that choice until it disappears from the fleet.
  useEffect(() => {
    if (!apis.length) return
    setSelectedId((current) =>
      current !== null && apis.some((api) => api.api_id === current) ? current : apis[0].api_id,
    )
  }, [apis])

  const selected = apis.find((api) => api.api_id === selectedId) ?? null

  // Latency, traffic and errors are the three series that grow every tick
  // rather than being recomputed from scratch: each fetch after the first
  // asks only for points at/after what's already buffered and appends,
  // instead of re-pulling the whole look-back window on every SSE frame.
  const latencyP50 = useIncrementalSeries(
    (since, signal) =>
      selectedId === null
        ? Promise.resolve([])
        : fetchLatency(selectedId, windowMin, 'p50', signal, since).then((r) => r.points),
    [selectedId, windowMin],
    tick,
  )
  const latencyP95 = useIncrementalSeries(
    (since, signal) =>
      selectedId === null
        ? Promise.resolve([])
        : fetchLatency(selectedId, windowMin, 'p95', signal, since).then((r) => r.points),
    [selectedId, windowMin],
    tick,
  )
  const latencyP99 = useIncrementalSeries(
    (since, signal) =>
      selectedId === null
        ? Promise.resolve([])
        : fetchLatency(selectedId, windowMin, 'p99', signal, since).then((r) => r.points),
    [selectedId, windowMin],
    tick,
  )
  const latencyLoading = latencyP50.loading || latencyP95.loading || latencyP99.loading

  const traffic = useIncrementalSeries(
    (since, signal) =>
      selectedId === null
        ? Promise.resolve([])
        : fetchTraffic(selectedId, windowMin, signal, since).then((r) => r.points),
    [selectedId, windowMin],
    tick,
  )

  const errorSeries = useIncrementalSeries(
    (since, signal) =>
      selectedId === null
        ? Promise.resolve([])
        : fetchErrors(selectedId, windowMin, signal, since).then((r) => r.points),
    [selectedId, windowMin],
    tick,
  )

  const forecast = useAsync(
    async (signal) =>
      selectedId === null ? null : fetchForecast(selectedId, FORECAST_HORIZON_MIN, signal),
    [selectedId, tick],
  )

  const endpoints = useAsync(
    async (signal) => (selectedId === null ? null : fetchEndpoints(selectedId, windowMin, signal)),
    [selectedId, windowMin, tick],
  )

  const healthTimeline = useAsync(
    async (signal) =>
      selectedId === null ? null : fetchHealthTimeline(selectedId, windowMin, signal),
    [selectedId, windowMin, tick],
  )

  const heatmap = useAsync(
    async (signal) => (selectedId === null ? null : fetchHeatmap(selectedId, windowMin, signal)),
    [selectedId, windowMin, tick],
  )

  const alerts = useAsync(
    async (signal) => snapshot?.alerts ?? (await fetchAlerts(windowMin, signal)),
    [windowMin, tick],
  )

  const models = useAsync(async (signal) => fetchModelMetrics(signal), [tick])

  // The container runtime, re-read on the same tick as everything else: a
  // service that starts, stops or changes its ports shows up within one frame,
  // with no separate timer and no manual refresh.
  const infra = useAsync(async (signal) => fetchInfra(signal), [tick])

  const summary = snapshot?.summary
  const errorTone = !summary
    ? 'neutral'
    : summary.error_rate >= 5
      ? 'critical'
      : summary.error_rate > 0
        ? 'warning'
        : 'good'

  // The narration. Every sentence below is derived from the series on screen,
  // so switching window or API rewrites the prose along with the charts — and
  // each one is withheld while its series is still in flight, because a
  // sentence describing data that has not arrived is the one way this pattern
  // can actively mislead.
  const verdict = fleetVerdict(apis)
  const outlook = trafficOutlook(traffic.points, forecast.data?.points ?? [], selected)
  const latencyText =
    selected && !latencyLoading
      ? latencyStory(
          latencyP50.points,
          latencyP95.points,
          latencyP99.points,
          selected.slo_latency_ms,
        )
      : null
  const trafficText =
    selected && !traffic.loading ? trafficStory(traffic.points, forecast.data?.points ?? []) : null
  const errorText =
    selected && !errorSeries.loading ? errorStory(errorSeries.points, selected.slo_target) : null
  const healthText =
    selected && healthTimeline.data
      ? healthStory(healthTimeline.data.points, selected.availability, selected.slo_target)
      : null
  const modelText = modelStory(models.data ?? [])

  // The infrastructure panels narrate themselves from the same snapshot they
  // render, so the sentence cannot claim a service the table below it does not
  // show — and both go quiet rather than guess while discovery is unavailable.
  const containers = infra.data?.containers ?? []
  const runningCount = containers.filter((container) => container.state === 'running').length
  const publishedCount = containers.reduce(
    (total, container) => total + container.endpoints.length,
    0,
  )
  const webGroups = infra.data?.environments ?? []
  const webCount = webGroups.reduce((total, group) => total + group.services.length, 0)
  const liveEnvCount = webGroups.filter((group) => group.services.length > 0).length

  /** Names the API a panel is scoped to, so a reader is never guessing. */
  const scope = (suffix: string) => (selected ? `${selected.name} · ${suffix}` : 'Select an API')

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

          <Segmented label="Window" options={WINDOWS} value={windowMin} onChange={setWindowMin} />

          <Segmented
            label="Reading as"
            options={
              [
                { label: 'Plain English', value: 'plain' },
                { label: 'Engineer', value: 'engineer' },
              ] as const
            }
            value={mode}
            onChange={(next: ReadingMode) => setMode(next)}
          />

          <Segmented
            label="Theme"
            options={
              [
                { label: 'Auto', value: 'system' },
                { label: 'Light', value: 'light' },
                { label: 'Dark', value: 'dark' },
              ] as const
            }
            value={choice}
            onChange={setChoice}
          />

          <div className="authbar">
            {auth.user ? (
              <>
                <span className="authbar__user">
                  {auth.user.email}
                  <span className="authbar__role">{auth.user.role}</span>
                </span>
                <button type="button" className="btn" onClick={() => setOpenModal('register-api')}>
                  Register API
                </button>
                <button type="button" className="btn btn--quiet" onClick={auth.signOut}>
                  Sign out
                </button>
              </>
            ) : (
              <button
                type="button"
                className="btn btn--primary"
                onClick={() => setOpenModal('signin')}
                disabled={auth.resolving}
              >
                Sign in
              </button>
            )}
          </div>
        </div>
      </header>

      {error ? (
        <p className="banner" role="alert">
          Cannot reach the PulseGrid API ({error}). Is the backend running on port 8000?
        </p>
      ) : null}

      {openModal === 'signin' ? (
        <Modal title="Sign in to PulseGrid" onClose={() => setOpenModal(null)}>
          <SignInForm auth={auth} onSuccess={() => setOpenModal(null)} />
        </Modal>
      ) : null}

      {openModal === 'register-api' && auth.token ? (
        <Modal title="Register an API" onClose={() => setOpenModal(null)}>
          <RegisterApiForm token={auth.token} onRegistered={() => setOpenModal(null)} />
        </Modal>
      ) : null}

      {/* The verdict. Everything below it is the evidence for this sentence. */}
      <section className={`verdict verdict--${verdict.tone}`} aria-label="Fleet verdict">
        <div className="verdict__main">
          <p className="verdict__eyebrow">
            Right now · {summary?.api_count ?? 0} {summary?.api_count === 1 ? 'API' : 'APIs'} · last{' '}
            {windowMin} minutes
          </p>
          <h2 className="verdict__headline">
            <span className="verdict__lead">{R(verdict.lead)}</span>{' '}
            <span className="verdict__rest">{R(verdict.rest)}</span>
          </h2>
          <p className="verdict__detail">{R(fleetDetail(summary, windowMin))}</p>
        </div>

        <div className="nextup">
          <p className="nextup__key">
            {say('What happens next', 'Forecast')}
            {selected ? ` · ${selected.name}` : ''}
          </p>
          <p className="nextup__value">{R(outlook.headline)}</p>
          <p className="nextup__detail">{R(outlook.detail)}</p>
        </div>
      </section>

      <section className="tiles" aria-label="Fleet summary">
        <StatTile
          index={0}
          label={say('How many APIs are we watching?', 'APIs monitored')}
          value={summary ? String(summary.api_count) : '—'}
          sub={say('every one of them measured live', 'registered targets')}
          tag="fleet"
        />
        <StatTile
          index={1}
          label={say('How much traffic came through?', 'Requests')}
          value={summary ? compact(summary.total_requests) : '—'}
          sub={R(requestsSub(summary, windowMin))}
          tag="requests"
        />
        <StatTile
          index={2}
          label={say('How many of those failed?', 'Error rate')}
          value={summary ? percent(summary.error_rate) : '—'}
          tone={errorTone}
          sub={R(errorSub(summary))}
          tag="5xx + transport"
        />
        <StatTile
          index={3}
          label={say('How long does a slow request take?', 'p95 latency')}
          value={summary ? millis(summary.p95_ms) : '—'}
          sub={R(latencySub(summary, windowMin))}
          tag="p95"
        />
        <StatTile
          index={4}
          label={say('What still needs a human?', 'Open alerts')}
          value={summary ? String(summary.open_alerts) : '—'}
          tone={summary && summary.open_alerts > 0 ? 'warning' : 'good'}
          sub={R(alertsSub(summary))}
          tag="alerts"
        />
      </section>

      <main className="bento">
        <Panel
          index={0}
          span={4}
          tall
          title={say('Which APIs are in trouble?', 'Fleet')}
          hint={say('Worst first — the top row is the thing to fix', 'Worst health score first')}
          lede={say(
            'Pick one to load every chart below against it.',
            'Selection scopes every panel below.',
          )}
        >
          <ApiList apis={apis} selectedId={selectedId} onSelect={setSelectedId} mode={mode} />
        </Panel>

        <Panel
          index={1}
          span={8}
          title={say('How long are people waiting?', 'Latency percentiles')}
          hint={scope(say('the typical wait, and the worst one', 'p50 / p95 / p99'))}
          lede={latencyText ? R(latencyText.lede) : undefined}
          readout={latencyText ? R(latencyText.readout) : undefined}
        >
          {selected && !latencyLoading ? (
            <LatencyChart
              p50={latencyP50.points}
              p95={latencyP95.points}
              p99={latencyP99.points}
              sloMs={selected.slo_latency_ms}
              tokens={tokens}
              mode={mode}
            />
          ) : (
            <Empty message={latencyLoading ? 'Loading…' : 'No API selected.'} />
          )}
        </Panel>

        <Panel
          index={2}
          span={8}
          title={say('How busy will we be?', 'Traffic and forecast')}
          hint={scope(
            say(
              `requests per minute, plus the next ${FORECAST_HORIZON_MIN}`,
              `requests per minute · ${FORECAST_HORIZON_MIN}m horizon`,
            ),
          )}
          lede={trafficText ? R(trafficText.lede) : undefined}
          readout={trafficText ? R(trafficText.readout) : undefined}
        >
          {selected && !traffic.loading ? (
            <TrafficChart
              traffic={traffic.points}
              forecast={forecast.data?.points ?? []}
              forecastFrom={forecast.data?.generated_at ?? null}
              tokens={tokens}
              mode={mode}
            />
          ) : (
            <Empty message={traffic.loading ? 'Loading…' : 'No API selected.'} />
          )}
        </Panel>

        <Panel
          index={3}
          span={6}
          title={say('How often do requests fail?', 'Error rate')}
          hint={scope(say('against the failure allowance', 'against the error budget'))}
          lede={errorText ? R(errorText.lede) : undefined}
          readout={errorText ? R(errorText.readout) : undefined}
        >
          {selected && !errorSeries.loading ? (
            <ErrorChart
              errors={errorSeries.points}
              sloTarget={selected.slo_target}
              tokens={tokens}
              mode={mode}
            />
          ) : (
            <Empty message={errorSeries.loading ? 'Loading…' : 'No API selected.'} />
          )}
        </Panel>

        <Panel
          index={4}
          span={6}
          title={say('Did we keep our promise?', 'Health timeline & SLA')}
          hint={scope(say('health over time, and availability', 'score history vs. objective'))}
          lede={healthText ? R(healthText.lede) : undefined}
          readout={healthText ? R(healthText.readout) : undefined}
          actions={
            selected ? (
              <SlaGauge availability={selected.availability} sloTarget={selected.slo_target} />
            ) : null
          }
        >
          {selected && healthTimeline.data ? (
            <HealthTimelineChart points={healthTimeline.data.points} tokens={tokens} mode={mode} />
          ) : (
            <Empty message={healthTimeline.loading ? 'Loading…' : 'No API selected.'} />
          )}
        </Panel>

        <Panel
          index={5}
          span={5}
          title={say("What changed that shouldn't have?", 'Detected anomalies')}
          hint={say(
            'found automatically, explained in words',
            'robust z-score + IsolationForest, with reasons',
          )}
          lede={say(
            'Each one names the signal that moved, what it normally is, and what it is now.',
            'Each carries its signal, expected band and detector confidence.',
          )}
        >
          <AlertFeed alerts={alerts.data ?? []} mode={mode} />
        </Panel>

        <Panel
          index={6}
          span={7}
          title={say('Which paths are slowest?', 'Endpoint breakdown')}
          hint={scope('slowest first')}
          lede={say(
            'Every path this API serves. A red figure is one that broke its target.',
            'Per-endpoint Golden Signals; red exceeds SLO.',
          )}
        >
          <EndpointTable
            endpoints={endpoints.data?.endpoints ?? []}
            sloMs={selected?.slo_latency_ms ?? 0}
            mode={mode}
          />
        </Panel>

        <Panel
          index={7}
          span={4}
          title={say('Which requests fail most?', 'Top failing endpoints')}
          hint={say('by share of requests that errored', 'by error rate, this window')}
        >
          <TopFailingEndpoints endpoints={endpoints.data?.endpoints ?? []} />
        </Panel>

        <Panel
          index={8}
          span={4}
          title={say('Which requests are slowest?', 'Top slow endpoints')}
          hint={say('by how long a slow one takes', 'by p95 latency, this window')}
        >
          <TopSlowEndpoints endpoints={endpoints.data?.endpoints ?? []} />
        </Panel>

        <Panel
          index={9}
          span={4}
          title={say('Where does the traffic go?', 'Traffic distribution')}
          hint={say('share of all requests, busiest first', 'share of requests per endpoint')}
        >
          <TrafficDistribution endpoints={endpoints.data?.endpoints ?? []} />
        </Panel>

        <Panel
          index={10}
          span={8}
          title={say('When was each path busy?', 'Request heatmap')}
          hint={scope(say('endpoints down, time across', 'endpoints × time, this window'))}
          lede={say(
            'Darker means more requests in that minute. A dark band across one row is a path under load; a dark column is the whole API being hit at once.',
            'Single-hue sequential ramp on a square-root scale, binned to fixed columns.',
          )}
        >
          {selected && heatmap.data ? (
            <HeatmapChart cells={heatmap.data.cells} tokens={tokens} />
          ) : (
            <Empty message={heatmap.loading ? 'Loading…' : 'No API selected.'} />
          )}
        </Panel>

        <Panel
          index={11}
          span={4}
          title={say('Can you trust the prediction?', 'Model metrics')}
          hint={say('checked against what really happened', 'last refit vs. seasonal-naive baseline')}
          lede={R(modelText.lede)}
          readout={R(modelText.readout)}
        >
          <ModelPanel metrics={models.data ?? []} mode={mode} />
        </Panel>

        <Panel
          index={12}
          span={12}
          title={say('What is actually running?', 'Containers')}
          hint={
            infra.data?.scope
              ? say(
                  `the ${infra.data.scope} stack, read from Docker`,
                  `compose project ${infra.data.scope} · Docker Engine API`,
                )
              : say('read live from the container runtime', 'Docker Engine API')
          }
          lede={
            infra.data?.available
              ? say(
                  `${runningCount} of ${containers.length} services are up, publishing ${publishedCount} ${publishedCount === 1 ? 'address' : 'addresses'} on this machine. Every link below is built from the container's own port mapping, so it goes where the service actually is.`,
                  `${runningCount}/${containers.length} running · ${publishedCount} published port bindings. Ports, health and endpoints are read from the Docker Engine, not from docker-compose.yml.`,
                )
              : undefined
          }
        >
          <ContainerTable snapshot={infra.data} mode={mode} />
        </Panel>

        <Panel
          index={13}
          span={12}
          title={say('Where can I open each environment?', 'Web endpoints by environment')}
          hint={say('development, QA and production', 'grouped by deployment environment')}
          lede={
            infra.data?.available
              ? say(
                  `${webCount} ${webCount === 1 ? 'address is' : 'addresses are'} open in a browser right now, across ${liveEnvCount} of ${webGroups.length} environments. A service is filed by the environment it declares, so moving a stack between them needs no change here.`,
                  `${webCount} browsable endpoints across ${liveEnvCount}/${webGroups.length} environments. Classified from the container's environment label, falling back to its own ENV, then its project name.`,
                )
              : undefined
          }
        >
          <WebEnvironments snapshot={infra.data} mode={mode} />
        </Panel>
      </main>

      <footer className="foot">
        <span>
          {say(
            'Every number on this page was measured automatically — nothing here is typed in by hand.',
            'Collected through the reverse proxy, /v1/ingest and an active prober. Analytics read only from metric_rollup.',
          )}
        </span>
        <a href="/docs">API docs</a>
      </footer>
    </div>
  )
}
