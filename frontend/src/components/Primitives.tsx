/**
 * Small presentational building blocks shared across the dashboard.
 */

import { useEffect, useRef, useState, type ReactNode } from 'react'
import { motion, useReducedMotion } from 'motion/react'

import { percent, STATUS_LABEL } from '../format'
import { SEVERITY_COLOR, STATUS_COLOR } from '../theme'

/** Columns a panel may claim on the twelve-column bento grid. */
export type PanelSpan = 4 | 5 | 6 | 7 | 8 | 12

/** Props for {@link Panel}. */
export interface PanelProps {
  title: string
  hint?: string
  /**
   * One sentence above the body saying what this panel shows, with this
   * window's numbers already in it.
   */
  lede?: string
  /** One sentence below the body saying what its current shape means. */
  readout?: string
  actions?: ReactNode
  children: ReactNode
  /** Columns claimed on the bento grid. Defaults to a third of the width. */
  span?: PanelSpan
  /** Claim two grid rows, for a panel whose content is a long list. */
  tall?: boolean
  /**
   * Position in the reveal order. Panels enter on a stagger keyed to this, so
   * the eye is walked down the page rather than shown all of it at once.
   */
  index?: number
}

/** Per-panel offset of the entrance stagger, in seconds. */
const STAGGER_S = 0.045

/** Stagger offsets past this index all fire together, so nothing feels late. */
const STAGGER_CAP = 8

/**
 * A titled card, and the unit the whole dashboard is built from.
 *
 * Beyond the title it carries two optional sentences — a `lede` above the body
 * and a `readout` below it. They are what turns a chart from something you have
 * to interpret into something that has already been read to you: the lede says
 * what is plotted with the real numbers in it, the readout says what the shape
 * currently means. Both are optional, so an engineer-mode panel can drop back
 * to bare instrumentation.
 *
 * Cards enter on a stagger derived from `index`, which is the one piece of
 * motion on the page: a bento grid that appears all at once gives the eye no
 * order to follow, and this dashboard has a triage order worth following.
 */
export function Panel({
  title,
  hint,
  lede,
  readout,
  actions,
  children,
  span = 4,
  tall,
  index = 0,
}: PanelProps) {
  const reduced = useReducedMotion()
  const classes = ['panel', `panel--span-${span}`]
  if (tall) classes.push('panel--tall')

  return (
    <motion.section
      className={classes.join(' ')}
      // Spelled out rather than `initial={false}`: the resting state of a
      // panel that never scrolls into view has to be *visible*, and a reader
      // who asked for less motion must not be the one who loses content.
      initial={reduced ? { opacity: 1, y: 0, scale: 1 } : { opacity: 0, y: 22, scale: 0.985 }}
      whileInView={{ opacity: 1, y: 0, scale: 1 }}
      viewport={{ once: true, amount: 0.12 }}
      transition={{
        duration: reduced ? 0 : 0.55,
        ease: [0.16, 1, 0.3, 1],
        delay: reduced ? 0 : Math.min(index, STAGGER_CAP) * STAGGER_S,
      }}
    >
      <header className="panel__head">
        <div className="panel__title">
          <h2>{title}</h2>
          {hint ? <p className="panel__hint">{hint}</p> : null}
        </div>
        {actions ? <div className="panel__actions">{actions}</div> : null}
      </header>
      {lede ? <p className="panel__lede">{lede}</p> : null}
      <div className="panel__body">{children}</div>
      {readout ? (
        <p className="panel__readout">
          <span className="panel__readoutKey">Reading it</span>
          {readout}
        </p>
      ) : null}
    </motion.section>
  )
}

/** Props for {@link StatTile}. */
export interface StatTileProps {
  /** In plain mode this is a question; in engineer mode, the measure's name. */
  label: string
  value: string
  sub?: string
  /**
   * The measure this tile reports, in the language the API uses. Anchors a
   * plain-English question to the thing an operator would go and query.
   */
  tag?: string
  /** Tints the value when the tile is reporting something bad. */
  tone?: 'neutral' | 'good' | 'warning' | 'critical'
  /** Position in the reveal order, matching {@link Panel}. */
  index?: number
}

/** How long the change highlight stays on a tile after its value updates. */
const FLASH_MS = 600

/**
 * A single headline number, framed by the question it answers.
 *
 * Deliberately not a chart: one value over one window has no shape worth
 * plotting. In plain mode the label carries the whole question ("How many of
 * those failed?"), because a number under a noun is a fact while a number under
 * a question is an answer — and an answer is what someone at the back of a room
 * can actually use.
 *
 * Briefly highlights itself whenever `value` changes so a live SSE-driven tile
 * reads as *updating* rather than the page having silently refreshed under it.
 */
export function StatTile({ label, value, sub, tag, tone = 'neutral', index = 0 }: StatTileProps) {
  const previous = useRef(value)
  const [flash, setFlash] = useState(false)
  const reduced = useReducedMotion()

  useEffect(() => {
    if (previous.current === value) return
    previous.current = value
    setFlash(true)
    const timer = window.setTimeout(() => setFlash(false), FLASH_MS)
    return () => window.clearTimeout(timer)
  }, [value])

  return (
    <motion.div
      className={flash ? `tile tile--${tone} tile--flash` : `tile tile--${tone}`}
      initial={reduced ? { opacity: 1, y: 0 } : { opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        duration: reduced ? 0 : 0.5,
        ease: [0.16, 1, 0.3, 1],
        delay: reduced ? 0 : index * 0.05,
      }}
    >
      <span className="tile__label">{label}</span>
      <strong className="tile__value">{value}</strong>
      <span className="tile__sub">{sub ?? ' '}</span>
      {tag ? <span className="tile__tag">{tag}</span> : null}
    </motion.div>
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

/** Props for {@link Modal}. */
export interface ModalProps {
  title: string
  onClose: () => void
  children: ReactNode
}

/**
 * A centred dialog over a dismissable scrim — used for sign-in and
 * API-registration, the two flows that need focused input rather than a
 * dashboard panel.
 *
 * Closes on Escape or a click outside the dialog; a click inside is stopped
 * from bubbling to the scrim so it doesn't close itself while someone's
 * filling in a field.
 */
export function Modal({ title, onClose, children }: ModalProps) {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  return (
    <div className="modal__scrim" onClick={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(event) => event.stopPropagation()}
      >
        <header className="modal__head">
          <h2>{title}</h2>
          <button type="button" className="modal__close" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </header>
        <div className="modal__body">{children}</div>
      </div>
    </div>
  )
}
