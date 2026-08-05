/**
 * The dashboard's charts.
 *
 * Conventions applied to all of them, so the set reads as one system:
 *
 * * One y-axis per chart. Two measures of different scale get two charts, never
 *   a second axis — a dual-axis chart lets the author choose the crossing point
 *   and therefore the conclusion.
 * * 3px lines, no per-point dots (they turn a 60-minute window into confetti),
 *   recessive grid and axes, and a legend whenever more than one series is on
 *   screen so identity never rests on colour alone.
 * * Series colours come from the validated categorical slots in `theme.ts`, in
 *   fixed order — p50 is always slot 1 whether or not p99 is on screen.
 * * Everything is sized for a room, not a laptop: the type on the axes and the
 *   weight of the lines assume the reader may be several metres from a
 *   projected copy of this page.
 *
 * Series names follow the reading mode. In plain mode a percentile is named by
 * the person it describes ("the unlucky 1 in 20") rather than by its statistic,
 * because "p95" is only meaningful to someone who already knows what it means —
 * and that reader has the engineer mode waiting for them.
 */

import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceArea,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { clock, millis, percent } from '../format'
import type { ReadingMode } from '../narrate'
import type { ChartTokens } from '../theme'
import type { ForecastPoint, HealthTimelinePoint, HeatmapCell, TimeseriesPoint } from '../types'
import { Empty } from './Primitives'

/** Height every chart renders at, so the panels line up across the grid. */
const CHART_HEIGHT = 300

/** Axis and annotation type size. Sized to survive projection, not to fit. */
const TICK_PX = 13

/** Annotation type size — one step up from the axes, since it carries meaning. */
const NOTE_PX = 14

/** Series stroke width. Thin lines are the first thing a projector loses. */
const STROKE = 3

/** A p99 excursion is only worth annotating once it is this far above typical. */
const PEAK_RATIO = 1.6

/** Pick a string for the reading mode in force. */
function say(mode: ReadingMode, plain: string, engineer: string): string {
  return mode === 'plain' ? plain : engineer
}

/** One row of a chart's data, keyed by epoch milliseconds. */
interface Row {
  t: number
  [series: string]: number | number[] | undefined
}

/**
 * Merge several named series into rows keyed by bucket.
 *
 * @param series Named point lists; each may have its own gaps.
 * @returns Rows sorted ascending by time.
 */
function mergeSeries(series: Record<string, TimeseriesPoint[]>): Row[] {
  const rows = new Map<number, Row>()
  for (const [name, points] of Object.entries(series)) {
    for (const point of points) {
      const t = new Date(point.bucket).getTime()
      const row = rows.get(t) ?? { t }
      row[name] = point.value
      rows.set(t, row)
    }
  }
  return [...rows.values()].sort((a, b) => a.t - b.t)
}

/**
 * Shared axis/grid configuration.
 *
 * @param tokens The palette for the current surface.
 * @param yFormatter Renders one y tick.
 * @param yDomain Fixes the y range. Pass it for any measure with a meaningful
 *   scale of its own — a 0-100 score auto-fitted to [88, 98] turns ordinary
 *   noise into a cliff, and hides any threshold that falls outside the data.
 */
function axes(
  tokens: ChartTokens,
  yFormatter: (value: number) => string,
  yDomain?: [number, number],
) {
  return (
    <>
      <CartesianGrid stroke={tokens.grid} strokeDasharray="0" vertical={false} />
      <XAxis
        dataKey="t"
        type="number"
        scale="time"
        domain={['dataMin', 'dataMax']}
        tickFormatter={(value: number) => clock(new Date(value).toISOString())}
        stroke={tokens.axis}
        tick={{ fill: tokens.muted, fontSize: TICK_PX }}
        tickLine={false}
        minTickGap={52}
        tickMargin={10}
      />
      <YAxis
        stroke={tokens.axis}
        tick={{ fill: tokens.muted, fontSize: TICK_PX }}
        tickLine={false}
        axisLine={false}
        width={64}
        domain={yDomain}
        tickFormatter={yFormatter}
      />
    </>
  )
}

/** Margin every chart uses. Generous at the top so annotations do not clip. */
const MARGIN = { top: 26, right: 16, bottom: 4, left: 0 }

/**
 * One entry of a Recharts tooltip payload.
 *
 * Structurally compatible with Recharts' own `TooltipPayloadEntry`, which is
 * not exported; `value` has to admit the readonly array form the range `Area`
 * produces, even though only the scalar case is rendered.
 */
interface TooltipPayloadItem {
  name?: string | number
  value?: string | number | readonly (string | number)[]
  color?: string
  dataKey?: string | number | ((row: never) => unknown)
}

/**
 * Build the crosshair tooltip.
 *
 * @param format Renders one value.
 * @returns A Recharts `content` renderer.
 */
function tooltipContent(format: (value: number) => string) {
  return function TooltipBody(props: {
    active?: boolean
    label?: string | number
    payload?: readonly TooltipPayloadItem[]
  }) {
    if (!props.active || !props.payload?.length) return null
    return (
      <div className="tooltip">
        <span className="tooltip__time">{clock(new Date(Number(props.label)).toISOString())}</span>
        {props.payload
          .filter((item) => typeof item.value === 'number')
          .map((item) => (
            <span className="tooltip__row" key={String(item.dataKey)}>
              <span className="tooltip__swatch" style={{ background: item.color }} />
              <span className="tooltip__name">{item.name}</span>
              <span className="tooltip__value">{format(item.value as number)}</span>
            </span>
          ))}
      </div>
    )
  }
}

/** Legend rendered as HTML rather than SVG, so the labels stay selectable text. */
function Legend({ items }: { items: { label: string; color: string; dashed?: boolean }[] }) {
  return (
    <ul className="legend">
      {items.map((item) => (
        <li key={item.label}>
          <span
            className={item.dashed ? 'legend__mark legend__mark--dashed' : 'legend__mark'}
            style={{ background: item.color }}
            aria-hidden="true"
          />
          {item.label}
        </li>
      ))}
    </ul>
  )
}

/** Shared shape of a reference line's label, so all of them read alike. */
function noteLabel(value: string, tokens: ChartTokens, position: 'insideBottomLeft' | 'insideTopLeft' | 'insideTopRight') {
  return { value, fill: tokens.muted, fontSize: NOTE_PX, position, offset: 8 }
}

/** Props for {@link LatencyChart}. */
export interface LatencyChartProps {
  p50: TimeseriesPoint[]
  p95: TimeseriesPoint[]
  p99: TimeseriesPoint[]
  sloMs: number
  tokens: ChartTokens
  mode: ReadingMode
}

/**
 * Latency percentiles over the window, with the SLO drawn as a reference line
 * so "is this bad?" is answerable without reading the axis.
 *
 * The worst p99 minute is marked with a dot and its clock time whenever it is a
 * genuine excursion rather than ordinary noise. A spike a reader has to find is
 * a spike most readers will miss.
 */
export function LatencyChart({ p50, p95, p99, sloMs, tokens, mode }: LatencyChartProps) {
  const data = mergeSeries({ p50, p95, p99 })
  if (!data.length) return <Empty message="No latency recorded in this window yet." />

  const [c50, c95, c99] = tokens.series

  // The worst minute, annotated only when it stands clear of the typical one.
  const worst = p99.reduce<TimeseriesPoint | null>(
    (best, point) => (best === null || point.value > best.value ? point : best),
    null,
  )
  const typical = p99.length ? p99.reduce((sum, point) => sum + point.value, 0) / p99.length : 0
  const excursion = worst && typical > 0 && worst.value / typical >= PEAK_RATIO ? worst : null

  return (
    <>
      <Legend
        items={[
          { label: say(mode, 'Typical request (half are faster)', 'p50'), color: c50 },
          { label: say(mode, 'Slow request (1 in 20)', 'p95'), color: c95 },
          { label: say(mode, 'Worst request (1 in 100)', 'p99'), color: c99 },
        ]}
      />
      <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
        <ComposedChart data={data} margin={MARGIN}>
          {axes(tokens, (value) => `${Math.round(value)} ms`)}
          <Tooltip
            content={tooltipContent(millis)}
            cursor={{ stroke: tokens.axis, strokeWidth: 1 }}
          />
          {/* `extendDomain` so the promise is drawn even when every measured
              value sits well under it. "Am I inside the target?" is not
              answerable from a chart the target fell off the top of. */}
          <ReferenceLine
            y={sloMs}
            ifOverflow="extendDomain"
            stroke={tokens.status.warning}
            strokeDasharray="6 5"
            strokeWidth={2}
            label={noteLabel(
              say(mode, `the promise — stay under ${sloMs} ms`, `SLO ${sloMs} ms`),
              tokens,
              'insideBottomLeft',
            )}
          />
          <Line
            type="monotone"
            dataKey="p50"
            name={say(mode, 'Typical', 'p50')}
            stroke={c50}
            strokeWidth={STROKE}
            dot={false}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="p95"
            name={say(mode, 'Slow (1 in 20)', 'p95')}
            stroke={c95}
            strokeWidth={STROKE}
            dot={false}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="p99"
            name={say(mode, 'Worst (1 in 100)', 'p99')}
            stroke={c99}
            strokeWidth={STROKE}
            dot={false}
            isAnimationActive={false}
          />
          {excursion ? (
            <ReferenceDot
              x={new Date(excursion.bucket).getTime()}
              y={excursion.value}
              r={5}
              fill={c99}
              stroke={tokens.surface}
              strokeWidth={2}
              label={{
                value: `${clock(excursion.bucket)} · ${millis(excursion.value)}`,
                fill: c99,
                fontSize: NOTE_PX,
                position: 'top',
                offset: 10,
              }}
            />
          ) : null}
        </ComposedChart>
      </ResponsiveContainer>
    </>
  )
}

/** Props for {@link TrafficChart}. */
export interface TrafficChartProps {
  traffic: TimeseriesPoint[]
  forecast: ForecastPoint[]
  forecastFrom: string | null
  tokens: ChartTokens
  mode: ReadingMode
}

/**
 * Observed traffic and the model's prediction on one shared axis.
 *
 * Both series are requests per minute, so they belong on the same scale — and
 * the shaded 95% interval is what makes the forecast honest: a bare line would
 * imply a confidence the model does not have. The boundary between measurement
 * and prediction is drawn and labelled, because the two are not the same kind
 * of claim and the chart should not let them blur.
 */
export function TrafficChart({ traffic, forecast, forecastFrom, tokens, mode }: TrafficChartProps) {
  if (!traffic.length) return <Empty message="No traffic recorded in this window yet." />

  const rows: Row[] = mergeSeries({ actual: traffic })
  const origin = forecastFrom ? new Date(forecastFrom).getTime() : Date.now()
  const boundary = rows.length ? rows[rows.length - 1].t : origin

  for (const point of forecast) {
    rows.push({
      t: origin + point.horizon_min * 60_000,
      yhat: point.yhat,
      band: [point.yhat_lower, point.yhat_upper],
    })
  }
  rows.sort((a, b) => a.t - b.t)

  return (
    <>
      <Legend
        items={[
          { label: say(mode, 'What actually happened', 'Observed'), color: tokens.series[0] },
          {
            label: say(mode, 'What we predict (shaded = margin of error)', 'Forecast · 95% interval'),
            color: tokens.forecast,
            dashed: true,
          },
        ]}
      />
      <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
        <ComposedChart data={rows} margin={MARGIN}>
          {axes(tokens, (value) => `${Math.round(value)}`)}
          <Tooltip
            content={tooltipContent((value) => `${value.toFixed(1)} req/min`)}
            cursor={{ stroke: tokens.axis, strokeWidth: 1 }}
          />
          <Area
            dataKey="band"
            name={say(mode, 'Margin of error', '95% interval')}
            stroke="none"
            fill={tokens.forecastBand}
            isAnimationActive={false}
            connectNulls
          />
          {forecast.length ? (
            <ReferenceLine
              x={boundary}
              stroke={tokens.axis}
              strokeDasharray="4 4"
              strokeWidth={2}
              label={noteLabel(say(mode, 'now', 'now'), tokens, 'insideTopRight')}
            />
          ) : null}
          <Line
            type="monotone"
            dataKey="actual"
            name={say(mode, 'Actually happened', 'Observed')}
            stroke={tokens.series[0]}
            strokeWidth={STROKE}
            dot={false}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="yhat"
            name={say(mode, 'Predicted', 'Forecast')}
            stroke={tokens.forecast}
            strokeWidth={STROKE}
            strokeDasharray="7 5"
            dot={false}
            isAnimationActive={false}
            connectNulls
          />
        </ComposedChart>
      </ResponsiveContainer>
    </>
  )
}

/** Props for {@link ErrorChart}. */
export interface ErrorChartProps {
  errors: TimeseriesPoint[]
  sloTarget: number
  tokens: ChartTokens
  mode: ReadingMode
}

/**
 * Error rate over the window against the error budget implied by the SLO.
 *
 * One series, so no legend box — the panel title names it. The fill uses the
 * reserved `critical` status colour rather than a categorical slot, because the
 * measure *is* a failure rate.
 */
export function ErrorChart({ errors, sloTarget, tokens, mode }: ErrorChartProps) {
  const data = mergeSeries({ rate: errors })
  if (!data.length) return <Empty message="No requests recorded in this window yet." />

  const budgetPct = (1 - sloTarget) * 100
  return (
    <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
      <ComposedChart data={data} margin={MARGIN}>
        {axes(tokens, (value) => `${value.toFixed(value < 1 ? 1 : 0)}%`)}
        <Tooltip
          content={tooltipContent((value) => percent(value))}
          cursor={{ stroke: tokens.axis, strokeWidth: 1 }}
        />
        {/* Same reason as the latency SLO: a budget line that only appears
            once you have broken it is not a budget line. */}
        <ReferenceLine
          y={budgetPct}
          ifOverflow="extendDomain"
          stroke={tokens.status.warning}
          strokeDasharray="6 5"
          strokeWidth={2}
          label={noteLabel(
            say(
              mode,
              `the promise — stay under ${budgetPct.toFixed(2)}%`,
              `budget ${budgetPct.toFixed(2)}%`,
            ),
            tokens,
            'insideBottomLeft',
          )}
        />
        <Area
          type="monotone"
          dataKey="rate"
          name={say(mode, 'Requests that failed', 'Error rate')}
          stroke={tokens.status.critical}
          strokeWidth={STROKE}
          fill={tokens.status.critical}
          fillOpacity={0.16}
          isAnimationActive={false}
        />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

/** Score thresholds mirrored from the backend's traffic-light status bands. */
const HEALTHY_SCORE = 90
const DEGRADED_SCORE = 70

/** Props for {@link HealthTimelineChart}. */
export interface HealthTimelineChartProps {
  points: HealthTimelinePoint[]
  tokens: ChartTokens
  mode: ReadingMode
}

/**
 * An API's composite health score over time — the up/down history behind the
 * single "score right now" number on its fleet row.
 *
 * One series, so no legend box. The healthy band is tinted rather than merely
 * ruled: "the line should live in the green" is a shape a reader gets in one
 * glance, where two dashed thresholds have to be read and compared.
 */
export function HealthTimelineChart({ points, tokens, mode }: HealthTimelineChartProps) {
  const data = mergeSeries({
    score: points.map((point) => ({ bucket: point.bucket, value: point.score })),
  })
  if (!data.length) return <Empty message="No health history in this window yet." />

  return (
    <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
      {/* Fixed to the score's own 0-100 scale. Auto-fitting would stretch a
          two-point wobble across the whole panel, and would drop the healthy
          band entirely whenever no minute happened to reach 100. */}
      <ComposedChart data={data} margin={MARGIN}>
        {axes(tokens, (value) => `${Math.round(value)}`, [0, 100])}
        <Tooltip
          content={tooltipContent((value) => value.toFixed(1))}
          cursor={{ stroke: tokens.axis, strokeWidth: 1 }}
        />
        <ReferenceArea
          y1={HEALTHY_SCORE}
          y2={100}
          fill={tokens.status.good}
          fillOpacity={0.08}
          stroke="none"
        />
        <ReferenceLine
          y={HEALTHY_SCORE}
          stroke={tokens.status.good}
          strokeDasharray="6 5"
          strokeWidth={2}
          label={noteLabel(
            say(mode, 'above here = healthy', `healthy ${HEALTHY_SCORE}`),
            tokens,
            'insideTopLeft',
          )}
        />
        <ReferenceLine
          y={DEGRADED_SCORE}
          stroke={tokens.status.warning}
          strokeDasharray="6 5"
          strokeWidth={2}
          label={noteLabel(
            say(mode, 'below here = degraded', `degraded ${DEGRADED_SCORE}`),
            tokens,
            'insideBottomLeft',
          )}
        />
        <Line
          type="monotone"
          dataKey="score"
          name={say(mode, 'Health score', 'Health score')}
          stroke={tokens.series[0]}
          strokeWidth={STROKE}
          dot={false}
          isAnimationActive={false}
        />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

/** Parse a `#rrggbb` hex color into its RGB components. */
function hexToRgb(hex: string): [number, number, number] {
  const value = Number.parseInt(hex.replace('#', ''), 16)
  return [(value >> 16) & 255, (value >> 8) & 255, value & 255]
}

/** Number of heatmap columns to bin buckets into, regardless of window length. */
const HEATMAP_COLUMNS = 20

/** One binned column: its label and, per endpoint, its summed request count. */
interface HeatmapColumn {
  label: string
  byEndpoint: Map<string, number>
}

/**
 * Group raw per-minute heatmap cells into a fixed number of display columns.
 *
 * A 6-hour window has 360 one-minute buckets; rendering one column per bucket
 * would make the grid illegible and mostly off-screen. Binning to a constant
 * column count keeps the heatmap's shape independent of the look-back window.
 */
function binHeatmap(cells: HeatmapCell[], maxColumns: number): HeatmapColumn[] {
  const buckets = [...new Set(cells.map((cell) => cell.bucket))].sort()
  if (!buckets.length) return []
  const groupSize = Math.max(1, Math.ceil(buckets.length / maxColumns))
  const byKey = new Map(cells.map((cell) => [`${cell.bucket}|${cell.endpoint}`, cell.req_count]))

  const columns: HeatmapColumn[] = []
  for (let start = 0; start < buckets.length; start += groupSize) {
    const group = new Set(buckets.slice(start, start + groupSize))
    const byEndpoint = new Map<string, number>()
    for (const cell of cells) {
      if (!group.has(cell.bucket)) continue
      byEndpoint.set(
        cell.endpoint,
        (byEndpoint.get(cell.endpoint) ?? 0) + (byKey.get(`${cell.bucket}|${cell.endpoint}`) ?? 0),
      )
    }
    columns.push({ label: clock(buckets[start]), byEndpoint })
  }
  return columns
}

/** Props for {@link HeatmapChart}. */
export interface HeatmapChartProps {
  cells: HeatmapCell[]
  tokens: ChartTokens
}

/**
 * Request-volume heatmap: endpoints down the side, time across the top.
 *
 * Built as a plain HTML table rather than a canvas/SVG grid — it is also the
 * form's own accessible table view, every cell's exact count is in its
 * `title`, and no extra dependency is needed for what is fundamentally a
 * colored grid. Intensity is one hue (the chart's primary series colour) at
 * increasing opacity — a single-hue sequential ramp, never a second hue — on
 * a square-root scale so a handful of very busy cells don't wash out everyone
 * else at the low end.
 *
 * The ramp is spelled out in a legend below the grid: a colour scale nobody can
 * decode is decoration, and a reader should be able to say roughly how many
 * requests a given square stands for.
 */
export function HeatmapChart({ cells, tokens }: HeatmapChartProps) {
  if (!cells.length) return <Empty message="No traffic recorded in this window yet." />

  const columns = binHeatmap(cells, HEATMAP_COLUMNS)
  const totals = new Map<string, number>()
  for (const cell of cells) {
    totals.set(cell.endpoint, (totals.get(cell.endpoint) ?? 0) + cell.req_count)
  }
  const endpoints = [...totals.keys()].sort((a, b) => (totals.get(b) ?? 0) - (totals.get(a) ?? 0))
  const max = Math.max(1, ...columns.flatMap((column) => [...column.byEndpoint.values()]))
  const [r, g, b] = hexToRgb(tokens.series[0])

  /** Fill for a cell holding `value` requests. */
  const shade = (value: number) =>
    value === 0 ? 'transparent' : `rgba(${r}, ${g}, ${b}, ${0.12 + Math.sqrt(value / max) * 0.8})`

  return (
    <>
      <div className="tablewrap">
        <table className="heatmap">
          <thead>
            <tr>
              <th scope="col" />
              {columns.map((column, index) => (
                <th scope="col" key={column.label + index}>
                  {index % 3 === 0 ? column.label : ''}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {endpoints.map((endpoint) => (
              <tr key={endpoint}>
                <th scope="row">
                  <code>{endpoint}</code>
                </th>
                {columns.map((column, index) => {
                  const value = column.byEndpoint.get(endpoint) ?? 0
                  return (
                    <td
                      key={column.label + index}
                      title={`${endpoint} · ${column.label} · ${value} req`}
                    >
                      <span className="heatmap__cell" style={{ background: shade(value) }} />
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="heatscale">
        <span>quiet</span>
        {[0, 0.25 * max, 0.5 * max, 0.75 * max, max].map((value) => (
          <span key={value} className="heatscale__step" style={{ background: shade(value) }} />
        ))}
        <span>busiest · {Math.round(max)} req</span>
      </div>
    </>
  )
}
