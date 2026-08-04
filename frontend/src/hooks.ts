/**
 * Data-loading and theming hooks for the dashboard.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

import { fetchOverview, streamUrl } from './api'
import type { Snapshot, TimeseriesPoint } from './types'

/** Connection state of the live stream, surfaced in the header badge. */
export type LiveState = 'connecting' | 'live' | 'polling' | 'offline'

/** What {@link useLiveSnapshot} returns. */
export interface LiveSnapshot {
  snapshot: Snapshot | null
  state: LiveState
  error: string | null
  /** Bumped on every update, so dependent panels know to refetch. */
  tick: number
}

/** How often the polling fallback re-reads the overview, in milliseconds. */
const POLL_INTERVAL_MS = 10_000

/**
 * Subscribe to the live fleet snapshot.
 *
 * Prefers the SSE stream, which the backend pushes on its own cadence. If the
 * stream cannot be established — an intermediary that buffers `text/event-stream`,
 * a browser without `EventSource` — it degrades to polling `/v1/analytics/overview`
 * rather than showing an empty dashboard. The badge in the header says which
 * mode is in effect, so "live" is never claimed when it is not true.
 *
 * @param windowMin Look-back window each snapshot covers.
 * @returns The latest snapshot and the connection state.
 */
export function useLiveSnapshot(windowMin: number): LiveSnapshot {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null)
  const [state, setState] = useState<LiveState>('connecting')
  const [error, setError] = useState<string | null>(null)
  const [tick, setTick] = useState(0)

  const accept = useCallback((next: Snapshot) => {
    setSnapshot(next)
    setError(null)
    setTick((value) => value + 1)
  }, [])

  useEffect(() => {
    let cancelled = false
    let poller: number | undefined
    const controller = new AbortController()

    // Paint immediately from a plain request rather than waiting for the first
    // stream frame, which is up to SSE_HEARTBEAT_SECONDS away.
    fetchOverview(windowMin, controller.signal)
      .then((initial) => {
        if (!cancelled) accept(initial)
      })
      .catch((cause: unknown) => {
        if (!cancelled && !(cause instanceof DOMException)) {
          setError(cause instanceof Error ? cause.message : String(cause))
          setState('offline')
        }
      })

    const startPolling = () => {
      if (poller !== undefined || cancelled) return
      setState('polling')
      poller = window.setInterval(() => {
        fetchOverview(windowMin)
          .then((next) => {
            if (!cancelled) accept(next)
          })
          .catch(() => {
            if (!cancelled) setState('offline')
          })
      }, POLL_INTERVAL_MS)
    }

    if (typeof EventSource === 'undefined') {
      startPolling()
      return () => {
        cancelled = true
        controller.abort()
        if (poller !== undefined) window.clearInterval(poller)
      }
    }

    const source = new EventSource(streamUrl(windowMin))

    source.addEventListener('snapshot', (event) => {
      if (cancelled) return
      try {
        accept(JSON.parse((event as MessageEvent<string>).data) as Snapshot)
        setState('live')
      } catch {
        setError('received a malformed snapshot frame')
      }
    })

    source.addEventListener('heartbeat', () => {
      if (!cancelled) setState('live')
    })

    source.onerror = () => {
      // EventSource retries on its own, but a stream that never establishes
      // would otherwise leave the dashboard frozen; polling covers that case.
      if (!cancelled && source.readyState === EventSource.CLOSED) startPolling()
    }

    return () => {
      cancelled = true
      controller.abort()
      source.close()
      if (poller !== undefined) window.clearInterval(poller)
    }
  }, [windowMin, accept])

  return { snapshot, state, error, tick }
}

/**
 * Load a value that depends on the selected API and window.
 *
 * @param loader Fetches the value; receives an abort signal.
 * @param deps Values that invalidate the result when they change.
 * @returns The latest value, or `null` before the first successful load.
 */
export function useAsync<T>(
  loader: (signal: AbortSignal) => Promise<T>,
  deps: readonly unknown[],
): { data: T | null; loading: boolean } {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)

  // The dependency list is the caller's `deps`, forwarded verbatim. A linter
  // cannot see through that indirection, but re-running on the deps rather than
  // on the freshly created `loader` closure is exactly the intent: otherwise
  // every render would restart the request.
  // oxlint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    const controller = new AbortController()
    let cancelled = false
    setLoading(true)

    loader(controller.signal)
      .then((value) => {
        if (!cancelled) {
          setData(value)
          setLoading(false)
        }
      })
      .catch(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
      controller.abort()
    }
    // oxlint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  return { data, loading }
}

/** What {@link useIncrementalSeries} returns. */
export interface IncrementalSeries {
  points: TimeseriesPoint[]
  loading: boolean
}

/**
 * The bucket to resume an incremental fetch from.
 *
 * The *second*-to-last point, not the last: `metric_rollup`'s current minute
 * keeps accumulating as more requests land in it, so re-requesting from one
 * bucket earlier lets a still-forming bucket's value be replaced rather than
 * frozen at whatever it read when it first appeared.
 */
function resumeCursor(points: TimeseriesPoint[]): string | undefined {
  return points.length >= 2 ? points[points.length - 2].bucket : undefined
}

/** Merge freshly fetched points into the buffer, replacing same-bucket entries. */
function mergeByBucket(previous: TimeseriesPoint[], fresh: TimeseriesPoint[]): TimeseriesPoint[] {
  if (!fresh.length) return previous
  const byBucket = new Map(previous.map((point) => [point.bucket, point] as const))
  for (const point of fresh) byBucket.set(point.bucket, point)
  return [...byBucket.values()].sort((a, b) => a.bucket.localeCompare(b.bucket))
}

/**
 * Load a Golden-Signal series that grows by appending rather than by
 * re-fetching its whole window on every SSE tick.
 *
 * A full fetch runs whenever `resetDeps` changes (the caller switched API or
 * look-back window); every later tick asks the backend only for points at or
 * after {@link resumeCursor} and merges them in, so a live dashboard costs one
 * small request per tick per series instead of one full-window request.
 *
 * @param loader Fetches points; receives `undefined` for a full window fetch
 *   or an ISO bucket cursor for an incremental one.
 * @param resetDeps Values that trigger a full refetch when they change (e.g.
 *   `[apiId, windowMin]`). Forwarded verbatim as the effect's dependency list,
 *   same convention as {@link useAsync}.
 * @param tick Bumped by {@link useLiveSnapshot} on every SSE frame; each bump
 *   after the initial load triggers one incremental fetch.
 * @returns The buffered series and whether the initial load is in flight.
 */
export function useIncrementalSeries(
  loader: (since: string | undefined, signal: AbortSignal) => Promise<TimeseriesPoint[]>,
  resetDeps: readonly unknown[],
  tick: number,
): IncrementalSeries {
  const [points, setPoints] = useState<TimeseriesPoint[]>([])
  const [loading, setLoading] = useState(true)
  const cursorRef = useRef<string | undefined>(undefined)
  const readyRef = useRef(false)

  // oxlint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    const controller = new AbortController()
    let cancelled = false
    readyRef.current = false
    setLoading(true)

    loader(undefined, controller.signal)
      .then((fresh) => {
        if (cancelled) return
        setPoints(fresh)
        cursorRef.current = resumeCursor(fresh)
        readyRef.current = true
        setLoading(false)
      })
      .catch(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
      controller.abort()
    }
    // oxlint-disable-next-line react-hooks/exhaustive-deps
  }, resetDeps)

  useEffect(() => {
    if (!readyRef.current) return
    const controller = new AbortController()
    let cancelled = false

    loader(cursorRef.current, controller.signal)
      .then((fresh) => {
        if (cancelled) return
        setPoints((previous) => {
          const merged = mergeByBucket(previous, fresh)
          cursorRef.current = resumeCursor(merged)
          return merged
        })
      })
      .catch(() => {
        // A missed incremental tick self-heals on the next one; no need to
        // surface a transient network blip as a loading/error state.
      })

    return () => {
      cancelled = true
      controller.abort()
    }
    // oxlint-disable-next-line react-hooks/exhaustive-deps
  }, [tick])

  return { points, loading }
}

/** Theme preference: follow the OS, or an explicit override. */
export type ThemeChoice = 'system' | 'light' | 'dark'

const THEME_KEY = 'pulsegrid.theme'

/**
 * Manage the light/dark theme.
 *
 * Stamps `data-theme` on the document element so CSS can override the OS
 * preference in both directions, and reports the resolved mode so charts can
 * pick a palette stepped for the surface they actually render on.
 *
 * @returns The choice, a setter, and whether dark is currently resolved.
 */
export function useTheme(): {
  choice: ThemeChoice
  setChoice: (next: ThemeChoice) => void
  dark: boolean
} {
  const [choice, setChoice] = useState<ThemeChoice>(
    () => (localStorage.getItem(THEME_KEY) as ThemeChoice | null) ?? 'system',
  )
  const [systemDark, setSystemDark] = useState(
    () => window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false,
  )

  useEffect(() => {
    const query = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = (event: MediaQueryListEvent) => setSystemDark(event.matches)
    query.addEventListener('change', onChange)
    return () => query.removeEventListener('change', onChange)
  }, [])

  useEffect(() => {
    localStorage.setItem(THEME_KEY, choice)
    const root = document.documentElement
    if (choice === 'system') root.removeAttribute('data-theme')
    else root.setAttribute('data-theme', choice)
  }, [choice])

  return { choice, setChoice, dark: choice === 'system' ? systemDark : choice === 'dark' }
}
