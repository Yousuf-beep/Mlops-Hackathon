/**
 * The dashboard's charts.
 *
 * Conventions applied to all three, so the set reads as one system:
 *
 * * One y-axis per chart. Two measures of different scale get two charts, never
 *   a second axis — a dual-axis chart lets the author choose the crossing point
 *   and therefore the conclusion.
 * * 2px lines, no per-point dots (they turn a 60-minute window into confetti),
 *   recessive grid and axes, and a legend whenever more than one series is on
 *   screen so identity never rests on colour alone.
 * * Series colours come from the validated categorical slots in `theme.ts`, in
 *   fixed order — p50 is always slot 1 whether or not p99 is on screen.
 */

import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { clock, millis, percent } from '../format'
import type { ChartTokens } from '../theme'
import type { ForecastPoint, TimeseriesPoint } from '../types'
import { Empty } from './Primitives'

/** Height every chart renders at, so the panels line up across the grid. */
const CHART_HEIGHT = 232

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

/** Shared axis/grid configuration. */
function axes(tokens: ChartTokens, yFormatter: (value: number) => string) {
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
        tick={{ fill: tokens.muted, fontSize: 11 }}
        tickLine={false}
        minTickGap={40}
      />
      <YAxis
        stroke={tokens.axis}
        tick={{ fill: tokens.muted, fontSize: 11 }}
        tickLine={false}
        axisLine={false}
        width={54}
        tickFormatter={yFormatter}
      />
    </>
  )
}

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

/** Props for {@link LatencyChart}. */
export interface LatencyChartProps {
  p50: TimeseriesPoint[]
  p95: TimeseriesPoint[]
  p99: TimeseriesPoint[]
  sloMs: number
  tokens: ChartTokens
}

/**
 * Latency percentiles over the window, with the SLO drawn as a reference line
 * so "is this bad?" is answerable without reading the axis.
 */
export function LatencyChart({ p50, p95, p99, sloMs, tokens }: LatencyChartProps) {
  const data = mergeSeries({ p50, p95, p99 })
  if (!data.length) return <Empty message="No latency recorded in this window yet." />

  const [c50, c95, c99] = tokens.series
  return (
    <>
      <Legend
        items={[
          { label: 'p50', color: c50 },
          { label: 'p95', color: c95 },
          { label: 'p99', color: c99 },
        ]}
      />
      <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
        <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          {axes(tokens, (value) => `${Math.round(value)}`)}
          <Tooltip
            content={tooltipContent(millis)}
            cursor={{ stroke: tokens.axis, strokeWidth: 1 }}
          />
          <ReferenceLine
            y={sloMs}
            stroke={tokens.status.warning}
            strokeDasharray="4 4"
            label={{ value: `SLO ${sloMs} ms`, fill: tokens.muted, fontSize: 11, position: 'left' }}
          />
          <Line
            type="monotone"
            dataKey="p50"
            name="p50"
            stroke={c50}
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="p95"
            name="p95"
            stroke={c95}
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="p99"
            name="p99"
            stroke={c99}
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
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
}

/**
 * Observed traffic and the model's prediction on one shared axis.
 *
 * Both series are requests per minute, so they belong on the same scale — and
 * the shaded 95% interval is what makes the forecast honest: a bare line would
 * imply a confidence the model does not have.
 */
export function TrafficChart({ traffic, forecast, forecastFrom, tokens }: TrafficChartProps) {
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
          { label: 'Observed', color: tokens.series[0] },
          { label: 'Forecast (95% interval)', color: tokens.forecast, dashed: true },
        ]}
      />
      <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
        <ComposedChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          {axes(tokens, (value) => `${Math.round(value)}`)}
          <Tooltip
            content={tooltipContent((value) => `${value.toFixed(1)} req/min`)}
            cursor={{ stroke: tokens.axis, strokeWidth: 1 }}
          />
          <Area
            dataKey="band"
            name="95% interval"
            stroke="none"
            fill={tokens.forecastBand}
            isAnimationActive={false}
            connectNulls
          />
          {forecast.length ? (
            <ReferenceLine x={boundary} stroke={tokens.axis} strokeDasharray="3 3" />
          ) : null}
          <Line
            type="monotone"
            dataKey="actual"
            name="Observed"
            stroke={tokens.series[0]}
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="yhat"
            name="Forecast"
            stroke={tokens.forecast}
            strokeWidth={2}
            strokeDasharray="5 4"
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
}

/**
 * Error rate over the window against the error budget implied by the SLO.
 *
 * One series, so no legend box — the panel title names it. The fill uses the
 * reserved `critical` status colour rather than a categorical slot, because the
 * measure *is* a failure rate.
 */
export function ErrorChart({ errors, sloTarget, tokens }: ErrorChartProps) {
  const data = mergeSeries({ rate: errors })
  if (!data.length) return <Empty message="No requests recorded in this window yet." />

  const budgetPct = (1 - sloTarget) * 100
  return (
    <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
      <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        {axes(tokens, (value) => `${value.toFixed(value < 1 ? 1 : 0)}%`)}
        <Tooltip
          content={tooltipContent((value) => percent(value))}
          cursor={{ stroke: tokens.axis, strokeWidth: 1 }}
        />
        <ReferenceLine
          y={budgetPct}
          stroke={tokens.status.warning}
          strokeDasharray="4 4"
          label={{
            value: `budget ${budgetPct.toFixed(1)}%`,
            fill: tokens.muted,
            fontSize: 11,
            position: 'left',
          }}
        />
        <Area
          type="monotone"
          dataKey="rate"
          name="Error rate"
          stroke={tokens.status.critical}
          strokeWidth={2}
          fill={tokens.status.critical}
          fillOpacity={0.16}
          isAnimationActive={false}
        />
      </ComposedChart>
    </ResponsiveContainer>
  )
}
