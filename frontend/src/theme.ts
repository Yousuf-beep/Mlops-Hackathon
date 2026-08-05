/**
 * Chart palette and theme handling.
 *
 * Recharts needs colours as JavaScript values, not CSS custom properties, so
 * the palette lives here and the stylesheet mirrors the same hexes for the
 * surrounding chrome. Both modes are *selected* rather than auto-flipped: the
 * dark column is the same hues re-stepped for a dark surface.
 *
 * The categorical slots and the status colours are the validated defaults from
 * the project's visualization guidance. The three-slot categorical set clears
 * every all-pairs colour-vision gate in both modes, which is why the latency
 * chart tops out at three percentile series.
 */

/** Every colour a chart needs, for one mode. */
export interface ChartTokens {
  surface: string
  grid: string
  axis: string
  muted: string
  text: string
  series: readonly [string, string, string]
  forecast: string
  forecastBand: string
  status: Record<'good' | 'warning' | 'serious' | 'critical', string>
}

const LIGHT: ChartTokens = {
  surface: '#ffffff',
  grid: '#e1e0d9',
  axis: '#c3c2b7',
  muted: '#78766f',
  text: '#0b0b0b',
  series: ['#2a78d6', '#eb6834', '#1baf7a'],
  forecast: '#4a3aa7',
  forecastBand: 'rgba(74, 58, 167, 0.16)',
  status: { good: '#0ca30c', warning: '#fab219', serious: '#ec835a', critical: '#d03b3b' },
}

const DARK: ChartTokens = {
  surface: '#16171d',
  grid: '#2c2d34',
  axis: '#383a43',
  muted: '#8d8f9a',
  text: '#f3f4f6',
  series: ['#3987e5', '#d95926', '#199e70'],
  forecast: '#9085e9',
  forecastBand: 'rgba(144, 133, 233, 0.20)',
  status: { good: '#0ca30c', warning: '#fab219', serious: '#ec835a', critical: '#d03b3b' },
}

/**
 * Return the chart tokens for a mode.
 *
 * @param dark Whether the dark surface is in use.
 * @returns The palette to hand to Recharts.
 */
export function chartTokens(dark: boolean): ChartTokens {
  return dark ? DARK : LIGHT
}

/** Colour for an API's traffic-light status, paired always with its label. */
export const STATUS_COLOR: Record<string, string> = {
  healthy: '#0ca30c',
  degraded: '#fab219',
  critical: '#d03b3b',
  no_data: '#898781',
}

/** Colour for an alert severity. */
export const SEVERITY_COLOR: Record<string, string> = {
  info: '#2a78d6',
  warning: '#fab219',
  critical: '#d03b3b',
}

/**
 * Colour for a container's runtime state.
 *
 * The same four hues as {@link STATUS_COLOR}, so a green dot means the same
 * thing in the fleet list and in the containers panel. Every use pairs the dot
 * with its written label — a stopped container and an unhealthy one are both
 * "not green", and the difference between them is the whole point.
 */
export const RUNTIME_COLOR: Record<string, string> = {
  healthy: '#0ca30c',
  running: '#0ca30c',
  starting: '#fab219',
  restarting: '#fab219',
  paused: '#fab219',
  unhealthy: '#d03b3b',
  dead: '#d03b3b',
  exited: '#898781',
  created: '#898781',
  removing: '#898781',
  none: '#898781',
}
