# Product

## Register

product

## Users

Backend and platform engineers on small teams who run production APIs and cannot
afford — in money or in instrumentation effort — a conventional APM stack. They
arrive at PulseGrid in one of two contexts:

- **Triage.** Something is slow or failing right now. They need latency, errors,
  traffic and the *reason* in one screen, without pivoting between Grafana,
  a spreadsheet of SLOs, and a vendor dashboard.
- **Assurance.** A periodic check that the fleet is inside its SLOs and nothing
  is trending toward breach.

The job to be done: *point a base URL at PulseGrid and get answers about that API
without changing a line of its code.*

## Product Purpose

PulseGrid measures real, live APIs through a transparent reverse proxy, computes
Golden-Signal analytics, forecasts traffic with Holt-Winters, and detects
anomalies with ML that it then explains in plain English — on one PostgreSQL
instance and one FastAPI process.

Conventional stacks answer *what happened*. PulseGrid's reason to exist is
answering *why it happened* and *what happens next*. Success is an operator
resolving an incident without leaving the page, and trusting the numbers enough
not to double-check them elsewhere.

## Brand Personality

**Instrument, not app.** Precise, quiet, measured. The interface reads like a
piece of monitoring equipment: real numbers in a monospace face, restrained
color, no persuasion. Confidence comes from showing the measurement — the
expected range, the confidence score, the connection state — never from
asserting it.

Voice: declarative and specific. "241 requests, last 60 min" over "Blazing fast
insights." The product never claims a freshness it does not have; the header
badge says `Polling` when it is polling.

## Anti-references

- **The SaaS auth split-screen** — customer testimonial or gradient mesh on the
  left, form on the right. If the left panel could belong to any product, it is
  wrong. PulseGrid's front door shows PulseGrid working.
- **Vendor-dashboard maximalism** (New Relic, Dynatrace): every pixel a control,
  nothing legible at a glance.
- **Marketing-page confidence** in an operator tool: hero metrics that are
  fictional, feature-bullet card grids, persuasion where measurement belongs.
- Gradient text, glassmorphism, decorative motion, invented affordances for
  standard tasks.

## Design Principles

1. **Practice what you preach.** A monitoring product should be visibly
   monitoring itself. The login screen plots real traffic from this instance
   because a claim you can watch beats a claim you have to read.
2. **Never lie about freshness.** Live, polling, offline and stale are four
   different states and the UI distinguishes all four. A dashboard that
   misreports its own currency is worse than one that admits it degraded.
3. **Explanation beats alarm.** Every anomaly ships with its signal, its
   expected range and a sentence of why. A number without its expected range is
   not yet information.
4. **State is never color alone.** Traffic-light status always pairs a dot with
   its written label; SLA fill pairs position with a value.
5. **Earned familiarity.** Standard affordances for standard tasks. The tool
   should disappear into the operator's task, not perform.

## Accessibility & Inclusion

Target: **WCAG 2.2 AA**.

- Body text ≥4.5:1 against its surface in *both* themes; large text ≥3:1.
  `--muted` (#78766f) clears only 3.84:1 on the light plane — it is valid for
  ≥18px text and decoration, not for body copy or form labels. Use `--text-2`
  for anything a user must read.
- Placeholder text held to the same 4.5:1 as body text.
- Visible focus indicators on every interactive element; complete keyboard path
  through each flow.
- Errors and status changes announced via `aria-live`, not by color or position.
- Every animation has a `prefers-reduced-motion: reduce` alternative. Content is
  never gated behind a reveal transition.
- Chart series are chosen to clear all-pairs color-vision gates in both themes,
  which is why the latency panel tops out at three percentile series.
