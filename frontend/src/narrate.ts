/**
 * Plain-English narration for the dashboard.
 *
 * Every panel can be read two ways: as an instrument, in the terse
 * percentile-and-budget language an operator already knows, or as a sentence
 * anyone else in the room can follow. This module builds the second one, and
 * keeps the first beside it so switching between them is a toggle rather than
 * a redesign.
 *
 * Two rules hold throughout:
 *
 * * Every sentence is computed from the same series the chart draws. A
 *   narration that can drift from its chart is worse than none at all, because
 *   it reads with the same authority.
 * * A sentence never claims more than the data supports. Where a window is too
 *   short or a series is empty, the narration says so instead of rounding a
 *   missing number to zero.
 */

import { compact, millis, percent } from './format'
import type {
  ApiOverviewItem,
  ForecastPoint,
  HealthTimelinePoint,
  ModelMetrics,
  Summary,
  TimeseriesPoint,
} from './types'

/** Which register the dashboard is currently written in. */
export type ReadingMode = 'plain' | 'engineer'

/** The same fact, said two ways. */
export interface Phrase {
  plain: string
  engineer: string
}

/** A panel's two lines of prose: what it shows, and how to read it. */
export interface Story {
  /** Sits above the chart: what the chart is, with this window's numbers in it. */
  lede: Phrase
  /** Sits below the chart: what its current shape actually means. */
  readout: Phrase
}

/**
 * Build a {@link Phrase}.
 *
 * @param plain Sentence for a reader who does not run the service.
 * @param engineer Sentence for the operator who does.
 */
export function phrase(plain: string, engineer: string): Phrase {
  return { plain, engineer }
}

/**
 * Resolve a phrase for the reading mode in force.
 *
 * @param mode The current register.
 * @param value The phrase to resolve.
 */
export function read(mode: ReadingMode, value: Phrase): string {
  return mode === 'plain' ? value.plain : value.engineer
}

/* -------------------------------------------------------------------------- */
/* Small numeric helpers                                                       */
/* -------------------------------------------------------------------------- */

/** Mean of the last `count` points — steadier than the single latest one. */
function tailMean(points: TimeseriesPoint[], count = 5): number | null {
  if (!points.length) return null
  const tail = points.slice(-count)
  return tail.reduce((sum, point) => sum + point.value, 0) / tail.length
}

/** Largest value in a series, or `null` when it is empty. */
function peak(points: TimeseriesPoint[]): number | null {
  return points.length ? Math.max(...points.map((point) => point.value)) : null
}

/**
 * Restate a percentage as a count out of a thousand.
 *
 * "0.31%" is a number most readers have to convert before it means anything;
 * "3 in every 1,000" is already the thing they wanted to know.
 *
 * @param pct A percentage already scaled 0-100.
 */
function perThousand(pct: number): string {
  const n = pct * 10
  if (n === 0) return '0'
  if (n < 1) return n.toFixed(2)
  if (n < 10) return n.toFixed(1)
  return String(Math.round(n))
}

/** How long a wait feels, for the p95 tile's sub-line. */
function waitFeel(ms: number): string {
  if (ms < 100) return 'faster than a blink'
  if (ms < 300) return 'quick enough that nobody notices'
  if (ms < 1000) return 'a visible pause'
  return 'long enough that people give up'
}

/* -------------------------------------------------------------------------- */
/* The verdict                                                                 */
/* -------------------------------------------------------------------------- */

/** The one-line answer to "is anything wrong right now?". */
export interface Verdict {
  tone: 'good' | 'warning' | 'critical'
  /** The clause that carries the tone, and gets the colour. */
  lead: Phrase
  /** The clause that puts it in proportion. */
  rest: Phrase
}

/**
 * State the fleet's condition in one sentence.
 *
 * The split into `lead` and `rest` is deliberate: the coloured half says what
 * is wrong and the plain half says how much of the fleet is unaffected, so
 * "two are struggling" never reads as "everything is on fire".
 */
export function fleetVerdict(apis: ApiOverviewItem[]): Verdict {
  if (!apis.length) {
    return {
      tone: 'good',
      lead: phrase('Nothing is being watched yet.', 'No targets registered.'),
      rest: phrase(
        'Register an API and PulseGrid starts measuring it on the next request.',
        'POST /v1/apis to begin ingest.',
      ),
    }
  }

  const live = apis.filter((api) => api.status !== 'no_data')
  if (!live.length) {
    return {
      tone: 'warning',
      lead: phrase('No traffic yet.', 'No samples in window.'),
      rest: phrase(
        `All ${apis.length} registered ${apis.length === 1 ? 'API has' : 'APIs have'} been quiet for this whole window.`,
        `${apis.length} target${apis.length === 1 ? '' : 's'} registered · 0 requests observed.`,
      ),
    }
  }

  const troubled = live.filter((api) => api.status !== 'healthy')
  if (!troubled.length) {
    return {
      tone: 'good',
      lead: phrase('Everything is healthy.', 'All targets within SLO.'),
      rest: phrase(
        `All ${live.length} ${live.length === 1 ? 'API is' : 'APIs are'} answering inside their targets.`,
        `${live.length} target${live.length === 1 ? '' : 's'} inside error budget.`,
      ),
    }
  }

  const hurt = troubled.length
  const fine = live.length - hurt
  return {
    tone: troubled.some((api) => api.status === 'critical') ? 'critical' : 'warning',
    lead: phrase(
      `${hurt} ${hurt === 1 ? 'API is' : 'APIs are'} struggling.`,
      `${hurt} target${hurt === 1 ? '' : 's'} below SLO.`,
    ),
    rest: phrase(
      fine ? `The other ${fine} ${fine === 1 ? 'is' : 'are'} fine.` : 'Nothing else is running clean.',
      fine ? `${fine} within error budget.` : 'No targets within budget.',
    ),
  }
}

/**
 * The paragraph under the verdict: what this page is actually doing.
 *
 * Present tense and specific to the window on screen, so it doubles as a
 * statement of how much evidence the rest of the page is standing on.
 */
export function fleetDetail(summary: Summary | undefined, windowMin: number): Phrase {
  const requests = summary ? compact(summary.total_requests) : 'no'
  return phrase(
    `PulseGrid has measured ${requests} requests across ${summary?.api_count ?? 0} APIs in the last ${windowMin} minutes. It times every call, counts the ones that fail, predicts how busy things will get, and raises an alert when a service drifts away from its own normal.`,
    `${requests} requests over ${windowMin}m across ${summary?.api_count ?? 0} targets. Per-request telemetry via reverse proxy and active probe; latency percentiles and error budgets over rolling windows; Holt-Winters traffic forecast; robust z-score and IsolationForest anomaly detection.`,
  )
}

/* -------------------------------------------------------------------------- */
/* What happens next                                                           */
/* -------------------------------------------------------------------------- */

/** The forecast, said as a direction rather than a number. */
export interface Outlook {
  headline: Phrase
  detail: Phrase
}

/** Below this percentage change, the forecast is not saying anything useful. */
const FLAT_FORECAST_PCT = 5

/**
 * Turn the traffic forecast into a sentence about the next half hour.
 *
 * @param traffic Observed requests-per-minute over the window.
 * @param forecast The model's points, each with its prediction interval.
 * @param subject The API the forecast belongs to, named when it is in trouble.
 */
export function trafficOutlook(
  traffic: TimeseriesPoint[],
  forecast: ForecastPoint[],
  subject: ApiOverviewItem | null,
): Outlook {
  const now = tailMean(traffic)
  const ahead = forecast.length ? forecast[forecast.length - 1] : null

  if (now === null || !ahead || now <= 0) {
    return {
      headline: phrase('Not enough history yet', 'No forecast'),
      detail: phrase(
        'The forecast needs about ten minutes of traffic before it can say anything worth acting on.',
        'Insufficient history to fit; the model needs ~10 minutes of buckets.',
      ),
    }
  }

  const change = ((ahead.yhat - now) / now) * 100
  const flat = Math.abs(change) < FLAT_FORECAST_PCT
  const rising = change > 0
  const strain =
    subject && subject.status !== 'healthy'
      ? ` ${subject.name} is already struggling, so it will feel worse before it feels better.`
      : ''

  return {
    headline: phrase(
      flat ? 'About as busy as now' : `${rising ? 'Busier' : 'Quieter'} by ~${Math.abs(Math.round(change))}%`,
      `${Math.round(now)} → ${Math.round(ahead.yhat)} rpm`,
    ),
    detail: phrase(
      flat
        ? `Traffic should hold steady for the next ${ahead.horizon_min} minutes.${strain}`
        : `Traffic should ${rising ? 'climb' : 'fall'} over the next ${ahead.horizon_min} minutes.${strain}`,
      `${ahead.horizon_min}-min horizon · 95% PI [${Math.round(ahead.yhat_lower)}–${Math.round(ahead.yhat_upper)}] rpm.`,
    ),
  }
}

/* -------------------------------------------------------------------------- */
/* Answer tiles                                                                */
/* -------------------------------------------------------------------------- */

/** Sub-line for the requests tile: the same total, as a rate. */
export function requestsSub(summary: Summary | undefined, windowMin: number): Phrase {
  if (!summary) return phrase('—', '—')
  const perMin = summary.total_requests / Math.max(1, windowMin)
  return phrase(
    `about ${compact(perMin)} every minute`,
    `${perMin.toFixed(perMin < 10 ? 1 : 0)} rpm mean · ${windowMin}m`,
  )
}

/** Sub-line for the error tile: the rate, restated out of a thousand. */
export function errorSub(summary: Summary | undefined): Phrase {
  if (!summary) return phrase('—', '—')
  return phrase(
    `${perThousand(summary.error_rate)} in every 1,000 requests failed`,
    `${summary.error_rate.toFixed(2)}% · 5xx and transport failures`,
  )
}

/** Sub-line for the p95 tile: what that wait actually feels like. */
export function latencySub(summary: Summary | undefined, windowMin: number): Phrase {
  if (!summary) return phrase('—', '—')
  return phrase(
    `1 request in 20 waits this long — ${waitFeel(summary.p95_ms)}`,
    `request-weighted, ${windowMin}m window`,
  )
}

/** Sub-line for the alerts tile. */
export function alertsSub(summary: Summary | undefined): Phrase {
  if (!summary) return phrase('—', '—')
  return summary.open_alerts > 0
    ? phrase('nobody has fixed these yet', 'firing, unresolved')
    : phrase('nothing is waiting on a human', 'none firing')
}

/* -------------------------------------------------------------------------- */
/* Per-API sentence, for the fleet list                                        */
/* -------------------------------------------------------------------------- */

/**
 * Say what is wrong with one API, in the order an operator would say it aloud.
 *
 * Reads the same three signals the health score is built from — latency against
 * its target, errors against the budget, availability against the SLO — and
 * names only the ones that are actually breached, so a healthy row stays short.
 */
export function describeApi(api: ApiOverviewItem): Phrase {
  if (api.status === 'no_data') {
    return phrase('No requests in this window. Nothing to judge it on.', 'no samples in window')
  }

  const budgetPct = (1 - api.slo_target) * 100
  const faults: string[] = []
  if (api.p95_ms > api.slo_latency_ms) {
    faults.push(
      `Slow — a slow request takes ${millis(api.p95_ms)} against a ${api.slo_latency_ms} ms target.`,
    )
  }
  if (api.error_rate > budgetPct) {
    faults.push(
      `Failing — ${perThousand(api.error_rate)} in every 1,000 requests error out, and the allowance is ${perThousand(budgetPct)}.`,
    )
  }
  if (api.availability < api.slo_target) {
    faults.push(
      `Dropping requests — available ${percent(api.availability * 100, 2)} of the time, promised ${percent(api.slo_target * 100, 2)}.`,
    )
  }

  const engineer = `p95 ${millis(api.p95_ms)} / ${api.slo_latency_ms} ms · err ${percent(api.error_rate, 2)} / ${budgetPct.toFixed(2)}% · avail ${percent(api.availability * 100, 2)}`

  if (!faults.length) {
    return phrase(
      api.open_alerts > 0
        ? 'Inside every target, but something odd was detected.'
        : 'Fine. Inside every target.',
      engineer,
    )
  }
  return phrase(faults.join(' '), engineer)
}

/* -------------------------------------------------------------------------- */
/* Panel stories                                                               */
/* -------------------------------------------------------------------------- */

/** Nothing measured yet — said once, rather than as a zero. */
const NO_DATA: Story = {
  lede: phrase(
    'Nothing has been measured in this window yet.',
    'No buckets in window.',
  ),
  readout: phrase(
    'Send some traffic through the proxy, or widen the window at the top of the page.',
    'Widen the look-back window or check ingest.',
  ),
}

/** Latency percentiles, said as three kinds of user. */
export function latencyStory(
  p50: TimeseriesPoint[],
  p95: TimeseriesPoint[],
  p99: TimeseriesPoint[],
  sloMs: number,
): Story {
  const a = tailMean(p50)
  const b = tailMean(p95)
  const c = tailMean(p99)
  if (a === null || b === null || c === null) return NO_DATA

  const over = b > sloMs
  const gap = Math.abs(b - sloMs)
  const spread = a > 0 ? c / a : 0

  return {
    lede: phrase(
      `Half of all requests finish in ${millis(a)}. One in twenty takes ${millis(b)}. One in a hundred takes ${millis(c)} — that last one is the line worth watching.`,
      `p50 ${millis(a)} · p95 ${millis(b)} · p99 ${millis(c)} · target ${sloMs} ms`,
    ),
    readout: over
      ? phrase(
          `The dashed line is the promise: a slow request should land under ${sloMs} ms. It is currently ${millis(gap)} over.`,
          `p95 exceeds SLO by ${millis(gap)} · p99/p50 spread ${spread.toFixed(1)}×`,
        )
      : phrase(
          `A slow request lands under the ${sloMs} ms promise with ${millis(gap)} to spare. The worst one in a hundred is ${spread.toFixed(1)}× the typical wait.`,
          `p95 under SLO by ${millis(gap)} · p99/p50 spread ${spread.toFixed(1)}×`,
        ),
  }
}

/** Traffic and its forecast. */
export function trafficStory(traffic: TimeseriesPoint[], forecast: ForecastPoint[]): Story {
  const busiest = peak(traffic)
  if (busiest === null) return NO_DATA
  const horizon = forecast.length ? forecast[forecast.length - 1].horizon_min : 0

  return {
    lede: phrase(
      `The solid line is what actually happened. The dotted line is our best guess for the next ${horizon} minutes, and the shaded band is how wrong that guess could reasonably be.`,
      `Observed rpm with a Holt-Winters forecast over ${horizon}m and its 95% prediction interval.`,
    ),
    readout: phrase(
      `The busiest minute so far handled ${Math.round(busiest)} requests. If the prediction holds, add capacity before that arrives — not after people complain.`,
      `Peak ${Math.round(busiest)} rpm observed in window · forecast horizon ${horizon}m.`,
    ),
  }
}

/** Error rate against the budget the SLO implies. */
export function errorStory(errors: TimeseriesPoint[], sloTarget: number): Story {
  const now = tailMean(errors)
  const worst = peak(errors)
  if (now === null || worst === null) return NO_DATA

  const budgetPct = (1 - sloTarget) * 100
  const breached = worst > budgetPct

  return {
    lede: phrase(
      `We promised failures would stay under ${perThousand(budgetPct)} in every 1,000 requests. Right now it is ${perThousand(now)}.`,
      `${now.toFixed(2)}% observed against a ${budgetPct.toFixed(2)}% budget.`,
    ),
    readout: breached
      ? phrase(
          `The dashed line is that promise, and this window broke it: the worst minute reached ${percent(worst, 2)}.`,
          `Budget ${budgetPct.toFixed(2)}% · peak ${worst.toFixed(2)}% · breached.`,
        )
      : phrase(
          `The dashed line is that promise. This window never crossed it — the worst single minute reached ${percent(worst, 2)}.`,
          `Budget ${budgetPct.toFixed(2)}% · peak ${worst.toFixed(2)}% · within budget.`,
        ),
  }
}

/** Score below which the backend calls an API degraded. */
const DEGRADED_SCORE = 70

/** Availability against the SLO, plus the health score's own history. */
export function healthStory(
  points: HealthTimelinePoint[],
  availability: number,
  sloTarget: number,
): Story {
  if (!points.length) return NO_DATA
  const degraded = points.filter((point) => point.score < DEGRADED_SCORE).length
  const met = availability >= sloTarget

  return {
    lede: phrase(
      `We told customers this API would answer ${percent(sloTarget * 100, 2)} of the time. So far this window it managed ${percent(availability * 100, 2)}.`,
      `Availability ${percent(availability * 100, 2)} against a ${percent(sloTarget * 100, 2)} SLO · composite score history.`,
    ),
    readout: degraded
      ? phrase(
          `It spent ${degraded} ${degraded === 1 ? 'minute' : 'minutes'} below the "degraded" line. Even if it recovered on its own, that time still counts against the promise.`,
          `${degraded} bucket${degraded === 1 ? '' : 's'} below score ${DEGRADED_SCORE} · counted toward budget.`,
        )
      : phrase(
          met
            ? 'It never dropped into "degraded" during this window, and it is keeping the promise.'
            : 'It never dropped into "degraded", but availability is still short of the promise.',
          `0 buckets below score ${DEGRADED_SCORE} · SLO ${met ? 'met' : 'missed'}.`,
        ),
  }
}

/** Model names carrying the "what if we just guessed?" baseline. */
const BASELINE = 'naive'

/** Can the forecast be trusted? Answered by comparing it to guessing. */
export function modelStory(metrics: ModelMetrics[]): Story {
  if (!metrics.length) {
    return {
      lede: phrase(
        'No forecast has been fitted yet, so there is nothing to check it against.',
        'No refit recorded.',
      ),
      readout: phrase(
        'Metrics appear after the first scheduled forecast job runs.',
        'Awaiting first evaluation run.',
      ),
    }
  }

  const scored = metrics.filter((entry) => entry.mape != null)
  const baseline = scored.find((entry) => entry.model_name.includes(BASELINE))
  const champion = scored
    .filter((entry) => !entry.model_name.includes(BASELINE))
    .sort((a, b) => (a.mape ?? Infinity) - (b.mape ?? Infinity))[0]

  if (!champion?.mape) {
    return {
      lede: phrase(
        'The detectors have run, but no forecast accuracy has been scored yet.',
        'No MAPE recorded for the champion model.',
      ),
      readout: phrase(
        'Accuracy is measured by replaying the forecast against what actually happened.',
        'Backtest pending.',
      ),
    }
  }

  const ratio = baseline?.mape ? baseline.mape / champion.mape : null
  return {
    lede: phrase(
      `We check every forecast against what actually happened. It is currently off by about ${percent(champion.mape, 1)}.`,
      `Champion ${champion.model_name} · MAPE ${percent(champion.mape, 1)} · lower is better.`,
    ),
    readout: ratio
      ? phrase(
          ratio >= 1.05
            ? `That is roughly ${ratio.toFixed(1)}× more accurate than simply assuming "same as last time" — which is why this is the model driving the capacity alerts.`
            : `That is no better than simply assuming "same as last time", so treat the forecast as a hint rather than a plan.`,
          `Baseline ${baseline?.model_name} MAPE ${percent(baseline?.mape ?? 0, 1)} · ratio ${ratio.toFixed(2)}×.`,
        )
      : phrase(
          'There is no baseline to compare it against yet, so read the number on its own.',
          'No seasonal-naive baseline recorded.',
        ),
  }
}
