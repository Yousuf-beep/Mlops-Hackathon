/**
 * Presentation helpers shared by the tiles, tables and chart axes.
 */

/** Formats clock labels once rather than per tick, which is measurably cheaper. */
const CLOCK = new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit' })

/**
 * Render an ISO timestamp as a short clock label.
 *
 * @param iso ISO-8601 timestamp.
 * @returns e.g. `14:07`.
 */
export function clock(iso: string): string {
  return CLOCK.format(new Date(iso))
}

/**
 * Render how long ago something happened.
 *
 * @param iso ISO-8601 timestamp.
 * @returns e.g. `4m ago`, or `just now` inside a minute.
 */
export function since(iso: string): string {
  const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (seconds < 60) return 'just now'
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86_400) return `${Math.floor(seconds / 3600)}h ago`
  return `${Math.floor(seconds / 86_400)}d ago`
}

/**
 * Render a count compactly.
 *
 * @param value The number to render.
 * @returns e.g. `1.2k`, `18`.
 */
export function compact(value: number): string {
  if (value < 1000) return String(Math.round(value))
  if (value < 1_000_000) return `${(value / 1000).toFixed(value < 10_000 ? 1 : 0)}k`
  return `${(value / 1_000_000).toFixed(1)}M`
}

/**
 * Render a duration in milliseconds at a sensible precision.
 *
 * @param ms Milliseconds.
 * @returns e.g. `84 ms`, `1.24 s`.
 */
export function millis(ms: number): string {
  if (ms >= 1000) return `${(ms / 1000).toFixed(2)} s`
  return `${ms < 10 ? ms.toFixed(1) : Math.round(ms)} ms`
}

/**
 * Render a percentage.
 *
 * @param value The percentage, already scaled 0-100.
 * @param digits Decimal places.
 * @returns e.g. `2.41%`.
 */
export function percent(value: number, digits = 2): string {
  return `${value.toFixed(digits)}%`
}

/** Human-readable label for each traffic-light status. */
export const STATUS_LABEL: Record<string, string> = {
  healthy: 'Healthy',
  degraded: 'Degraded',
  critical: 'Critical',
  no_data: 'No data',
}
