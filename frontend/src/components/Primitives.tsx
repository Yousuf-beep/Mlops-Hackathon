/**
 * Small presentational building blocks shared across the dashboard.
 */

import { useEffect, useRef, useState, type ReactNode } from 'react'

import { percent, STATUS_LABEL } from '../format'
import { SEVERITY_COLOR, STATUS_COLOR } from '../theme'

/** Props for {@link Panel}. */
export interface PanelProps {
  title: string
  hint?: string
  actions?: ReactNode
  children: ReactNode
  /** Span two columns of the dashboard grid. */
  wide?: boolean
}

/**
 * A titled card. Every chart and table on the dashboard sits in one, so the
 * page reads as a set of answers rather than a wall of plots.
 */
export function Panel({ title, hint, actions, children, wide }: PanelProps) {
  return (
    <section className={wide ? 'panel panel--wide' : 'panel'}>
      <header className="panel__head">
        <div>
          <h2>{title}</h2>
          {hint ? <p className="panel__hint">{hint}</p> : null}
        </div>
        {actions ? <div className="panel__actions">{actions}</div> : null}
      </header>
      <div className="panel__body">{children}</div>
    </section>
  )
}

/** Props for {@link StatTile}. */
export interface StatTileProps {
  label: string
  value: string
  sub?: string
  /** Tints the value when the tile is reporting something bad. */
  tone?: 'neutral' | 'good' | 'warning' | 'critical'
}

/** How long the change highlight stays on a tile after its value updates. */
const FLASH_MS = 600

/**
 * A single headline number. Deliberately not a chart: one value over one window
 * has no shape worth plotting.
 *
 * Briefly highlights itself whenever `value` changes so a live SSE-driven tile
 * reads as *updating* rather than the page having silently refreshed under it.
 */
export function StatTile({ label, value, sub, tone = 'neutral' }: StatTileProps) {
  const previous = useRef(value)
  const [flash, setFlash] = useState(false)

  useEffect(() => {
    if (previous.current === value) return
    previous.current = value
    setFlash(true)
    const timer = window.setTimeout(() => setFlash(false), FLASH_MS)
    return () => window.clearTimeout(timer)
  }, [value])

  return (
    <div className={flash ? `tile tile--${tone} tile--flash` : `tile tile--${tone}`}>
      <span className="tile__label">{label}</span>
      <strong className="tile__value">{value}</strong>
      <span className="tile__sub">{sub ?? ' '}</span>
    </div>
  )
}

/** Props for {@link SlaGauge}. */
export interface SlaGaugeProps {
  availability: number
  sloTarget: number
}

/**
 * A compact SLA indicator: current availability against its objective.
 *
 * A filled track plus a tick mark at the target reads faster than a number
 * pair, and the fill's colour (good/critical) restates the same verdict the
 * position already shows, so the state is never colour-alone.
 */
export function SlaGauge({ availability, sloTarget }: SlaGaugeProps) {
  const met = availability >= sloTarget
  const fillPct = Math.min(100, Math.max(0, availability * 100))
  const targetPct = Math.min(100, Math.max(0, sloTarget * 100))

  return (
    <div
      className="sla"
      role="img"
      aria-label={`Availability ${percent(availability * 100, 2)} against a ${percent(targetPct, 2)} SLO target, ${met ? 'meeting' : 'missing'} it`}
    >
      <div className="sla__track">
        <div
          className={met ? 'sla__fill sla__fill--good' : 'sla__fill sla__fill--critical'}
          style={{ width: `${fillPct}%` }}
        />
        <div className="sla__target" style={{ left: `${targetPct}%` }} />
      </div>
      <span className="sla__label">
        {percent(availability * 100, 2)} <span className="sla__vs">/ {percent(targetPct, 2)} SLO</span>
      </span>
    </div>
  )
}

/**
 * A traffic-light status, always rendered as a dot *and* its label so the state
 * never depends on colour alone.
 */
export function StatusBadge({ status }: { status: string }) {
  return (
    <span className="badge">
      <span
        className="badge__dot"
        style={{ background: STATUS_COLOR[status] ?? STATUS_COLOR.no_data }}
        aria-hidden="true"
      />
      {STATUS_LABEL[status] ?? status}
    </span>
  )
}

/** Severity chip for the alert feed, likewise dot + label. */
export function SeverityBadge({ severity }: { severity: string }) {
  return (
    <span className="badge">
      <span
        className="badge__dot"
        style={{ background: SEVERITY_COLOR[severity] ?? STATUS_COLOR.no_data }}
        aria-hidden="true"
      />
      {severity}
    </span>
  )
}

/**
 * Placeholder shown where a panel has nothing to draw.
 *
 * An empty chart and a broken chart look identical, so this says which it is.
 */
export function Empty({ message }: { message: string }) {
  return <p className="empty">{message}</p>
}
