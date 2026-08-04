/**
 * PulseGrid live-traffic generator.
 *
 * Replaces the "demo-only" traffic problem: instead of the dashboard only
 * ever seeing the active prober's one request per API per
 * PROBE_INTERVAL_SECONDS, this drives real, varied load through PulseGrid's
 * own reverse proxy (`/proxy/{slug}/...`) so every request is measured
 * exactly like traffic against a real production API — it lands in
 * `request_log`, gets rolled up, and feeds analytics/forecasting/anomaly
 * detection with zero backend changes.
 *
 * Shape: one `ramping-arrival-rate` scenario whose stages alternate between
 * idle, normal, and burst/spike arrival rates, covering every pattern the
 * brief asks for (normal usage, bursts, spikes, idle periods) in a single
 * timeline. "Random failures" and "slow requests" come from *which* demo
 * endpoint gets hit, not from special-casing errors in this script: the
 * three demo APIs already seeded by `app/bootstrap.py` (`demo-fast`,
 * `demo-slow`, `demo-flaky`) each proxy to two real upstream routes — their
 * signature one plus the shared `/users/{id}` — picked with weighted
 * randomness. `demo-flaky` already fails ~10% of the time server-side, and
 * `/users/{id}` 404s for an out-of-range id, so both an error-class and a
 * not-found-class failure occur organically. An occasional request to an
 * unregistered slug produces a third failure shape (routing 404s) the same
 * way a mistyped real client call would.
 *
 * The scenario has a finite duration (the stages sum to a few minutes); the
 * `loadgen` compose service restarts it in a loop via `restart:
 * unless-stopped`, so the pattern repeats indefinitely without the script
 * needing its own infinite-loop bookkeeping.
 */

import http from 'k6/http'
import { check } from 'k6'

/** PulseGrid API base URL. Defaults to the compose service DNS name. */
const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000'

/**
 * Return a random synthetic user id, occasionally outside the valid range so
 * `/users/{id}` produces its own (404) failure mode alongside `/flaky`'s 500s.
 */
function randomUserId() {
  // ~8% land outside demo_target.VALID_USER_ID_RANGE (1..4999) on purpose.
  if (Math.random() < 0.08) return 0 // noqa-equivalent: synthetic load, not crypto
  return Math.floor(Math.random() * 5000) + 1
}

/**
 * Proxy paths to drive traffic through, each weighted by how often it should
 * be picked.
 *
 * Each demo API's `upstream_url` (set by `app/bootstrap.py`) is the bare
 * demo-target origin, so the remainder of the proxied path is forwarded
 * as-is — `/proxy/demo-fast/fast` reaches `/fast`, `/proxy/demo-fast/users/7`
 * reaches `/users/7`. Every registered API therefore gets *two* endpoints
 * (its signature route plus the shared `/users/{id}` route), which is what
 * gives the per-endpoint dashboard panels something to rank. One weighted
 * entry per API is a function so each pick gets a fresh random id; a final
 * fixed entry hits a deliberately unknown slug for organic 404 traffic (a
 * caller hitting a service that was never registered, or was since
 * deregistered).
 */
const TARGETS = [
  { weight: 32, path: () => '/proxy/demo-fast/fast' },
  { weight: 10, path: () => `/proxy/demo-fast/users/${randomUserId()}` },
  { weight: 18, path: () => '/proxy/demo-slow/slow' },
  { weight: 8, path: () => `/proxy/demo-slow/users/${randomUserId()}` },
  { weight: 18, path: () => '/proxy/demo-flaky/flaky' },
  { weight: 9, path: () => `/proxy/demo-flaky/users/${randomUserId()}` },
  { weight: 5, path: () => '/proxy/not-registered/ping' },
]

const TOTAL_WEIGHT = TARGETS.reduce((sum, target) => sum + target.weight, 0)

/** Pick one proxy path, respecting the configured weights. */
function pickTarget() {
  let roll = Math.random() * TOTAL_WEIGHT
  for (const target of TARGETS) {
    roll -= target.weight
    if (roll <= 0) return target
  }
  return TARGETS[0]
}

/**
 * Jitter a target arrival rate by up to `spread` in either direction.
 *
 * Evaluated once at module load — i.e. once per k6 process start, which is
 * once per `loadgen` container restart cycle (the scenario's stages sum to a
 * few minutes; `restart: unless-stopped` re-runs the whole file on completion,
 * see the module docstring). Without this, every cycle repeats an identical
 * shape and the anomaly detector's rolling baseline adapts to "the burst" as
 * normal after a cycle or two, so it stops firing — a real system's bursts
 * are not that predictable, and the demo should not train the detector to
 * ignore them.
 */
function jitter(target, spread = 0.35) {
  const factor = 1 + (Math.random() * 2 - 1) * spread
  return Math.max(1, Math.round(target * factor))
}

// Rates are deliberately modest: this fleet runs a single Postgres instance
// and single-worker demo services under `docker compose`, not a production
// cluster. The point is a visible, varied traffic *shape* — idle, normal,
// bursty, spiky — not maximum throughput, which would just saturate a dev
// laptop's proxy and read back as every API being "critical" all the time.
export const options = {
  scenarios: {
    fleet_traffic: {
      executor: 'ramping-arrival-rate',
      startRate: 1,
      timeUnit: '1s',
      preAllocatedVUs: 30,
      maxVUs: 80,
      stages: [
        { target: 1, duration: '20s' }, // idle: barely anyone calling
        { target: jitter(3), duration: '30s' }, // ramp into normal usage
        { target: jitter(3), duration: '40s' }, // sustained normal usage
        { target: jitter(12), duration: '15s' }, // sudden traffic spike
        { target: jitter(12), duration: '20s' }, // sustained burst
        { target: jitter(2), duration: '20s' }, // cool back down
        { target: 1, duration: '25s' }, // idle period again
        { target: jitter(5), duration: '30s' }, // ramp into a busier normal
        { target: jitter(5), duration: '45s' }, // sustained normal usage
        { target: jitter(16), duration: '10s' }, // sharper spike
        { target: jitter(16), duration: '15s' }, // sustained burst
        { target: 1, duration: '20s' }, // cool down to idle
      ],
    },
  },
  // No thresholds: `demo-flaky` and the unregistered slug are *meant* to
  // fail, and a threshold breach would abort the run instead of leaving the
  // dashboard something to detect.
  discardResponseBodies: true,
}

export default function traffic() {
  const target = pickTarget()
  const path = target.path()
  const response = http.get(`${BASE_URL}${path}`, {
    timeout: '20s',
    tags: { pulsegrid_target: path },
  })
  check(response, {
    'got a response': (r) => r.status !== 0,
  })
}
