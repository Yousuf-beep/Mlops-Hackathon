# PulseGrid — Architecture

## One-line pitch

PulseGrid monitors **real, live APIs** through a transparent reverse proxy,
computes Golden-Signal analytics (latency, traffic, errors, saturation),
detects anomalies with ML, and forecasts traffic — all on a single PostgreSQL
instance and a single FastAPI process.

## Problem statement

Teams running production APIs typically have three separate, badly connected
things: an APM vendor they can't afford at scale, a metrics stack (Prometheus +
Grafana) that requires instrumenting every service, and a spreadsheet where
someone tracks SLOs by hand. All three answer *what happened*. None of them
answer *why*, and none of them tell you what is about to happen.

PulseGrid collapses the three into one deployable system:

- **Zero-instrumentation collection.** Point a base URL at PulseGrid's proxy
  and every call is measured. No SDK, no code change, no sidecar.
- **Explained anomalies.** Every alert carries a natural-language reason and
  the expected range it violated, not just a threshold breach.
- **Forward-looking.** Traffic forecasts with prediction intervals, so capacity
  conversations happen before the incident.

## Data flow

```
                       ┌──────────────────────────────────────────┐
   real API clients ──▶│  FastAPI collector                       │
                       │                                          │
                       │  /proxy/{path}   transparent reverse proxy│──▶ live upstream APIs
                       │  POST /v1/ingest SDK push                 │      (incl. demo-target)
                       │  APScheduler     active prober            │◀─────────┘
                       └───────────────┬──────────────────────────┘
                                       │ append (write-heavy)
                                       ▼
                              ┌──────────────────┐
                              │   request_log    │  raw facts, append-only
                              │  BRIN(time)      │  one row per API call
                              │  BTREE(api,time) │
                              └────────┬─────────┘
                                       │ APScheduler rollup job, every 60s
                                       │ date_trunc('minute', time) GROUP BY
                                       ▼
                              ┌──────────────────┐
                              │  metric_rollup   │  per-minute aggregates
                              │ BTREE(api,bucket)│  read-heavy
                              │ UNIQUE(b,api,ep) │
                              └────────┬─────────┘
                                       │
              ┌────────────────────────┼────────────────────────┐
              ▼                        ▼                        ▼
      /v1/analytics/*          ML jobs (APScheduler)      GET /v1/stream
      latency|traffic|         forecasting.py  ──▶ forecast   (SSE, text/event-stream)
      errors|health|summary    anomaly.py      ──▶ alert
              │                        │                        │
              └────────────────────────┴────────────────────────┘
                                       ▼
                         React + Vite + Recharts dashboard
```

## Components

| Component | Responsibility | Phase |
| --- | --- | --- |
| `/proxy/{path}` | Transparent reverse proxy; measures every forwarded call | 2 |
| `POST /v1/ingest` | SDK/agent push path for services that can't be proxied | 2 |
| APScheduler prober | Actively probes registered APIs so idle services still produce signal | 2 |
| `request_log` | Raw append-only time-series facts | 1 |
| Rollup job | `date_trunc('minute', time)` aggregation into `metric_rollup` | 2 |
| `metric_rollup` | Pre-aggregated Golden Signals; the only table analytics reads | 1 |
| `/v1/analytics/*` | Latency, traffic, errors, per-API health score, fleet summary | 2 |
| `app/ml/forecasting.py` | Holt-Winters traffic forecast with prediction intervals | 3 |
| `app/ml/anomaly.py` | Robust z-score + IsolationForest, with explanations | 3 |
| `GET /v1/stream` | SSE channel pushing live frames to the dashboard | 1 (heartbeat) / 2 (data) |
| React dashboard | Recharts visualisation of every signal | 4 |

## Time-series strategy on plain PostgreSQL

This is the central database-design decision, and it is deliberate.

**The problem.** A monitoring system has two workloads with opposite shapes.
Collection is a high-rate stream of small inserts. Dashboards are wide range
scans that need aggregates over thousands of rows and must return in
milliseconds. Serving both from one table means every dashboard refresh scans
the raw log, and it gets slower every minute the system runs.

**The split.** `request_log` takes the writes; `metric_rollup` serves the
reads. A background job bridges them once a minute with
`date_trunc('minute', time)` GROUP BY queries. Dashboard queries then read a
few hundred pre-aggregated rows instead of millions of raw ones, and their cost
is bounded by the *window* they ask for rather than by total system uptime.

**The indexes.**

| Table | Index | Type | Why |
| --- | --- | --- | --- |
| `request_log` | `ix_request_log_time_brin (time)` | **BRIN** | The table is append-only, so it is already physically ordered by `time`. BRIN stores a min/max summary per block range instead of an entry per row, so a time-range scan skips almost every non-matching block — at an index size of kilobytes rather than the hundreds of megabytes a B-tree would cost at ingest scale. |
| `request_log` | `ix_request_log_api_id_time (api_id, time DESC)` | B-tree | BRIN is block-level and cannot answer "last 15 minutes **for API 3**" selectively. `DESC` matches the `ORDER BY ... DESC LIMIT n` shape the rollup job and drill-down queries issue. |
| `metric_rollup` | `ix_metric_rollup_api_id_bucket (api_id, bucket DESC)` | B-tree | Covers every dashboard window query. |
| `metric_rollup` | `uq_metric_rollup_bucket_api_endpoint (bucket, api_id, endpoint)` | UNIQUE | Makes the rollup job idempotent: it re-processes a short trailing window for late-arriving rows and must upsert, not duplicate. |
| `users` | `ix_users_email (email)` | UNIQUE | Login lookup. |
| `alert`, `forecast` | `(api_id, <timestamp> DESC)` | B-tree | "Recent items for this API", the only read pattern either table has. |

**Why not a time-series database?** TimescaleDB, InfluxDB or Prometheus would
each hand us hypertables or a TSDB engine for free — and each would add an
operational dependency the judging environment has to install and that the team
has to debug at 3am. The techniques that make those systems fast (physical time
ordering, block-range summaries, pre-aggregation, retention windows) are all
available on stock PostgreSQL. Choosing them explicitly, and being able to
explain why, is the point.

## Key technology decisions

| Decision | Chosen | Rejected | Why |
| --- | --- | --- | --- |
| Background jobs | APScheduler in-process | Celery + Redis | The jobs are short, idempotent and single-tenant. Celery would add a broker, a worker image and a second deployment for no gain, and would break the "one `docker compose up`" story. |
| Live updates | SSE (`text/event-stream`) | WebSockets | Traffic is strictly server→client. SSE is plain HTTP, survives proxies without an upgrade handshake, and browsers reconnect automatically. |
| DB driver | psycopg 3 (`postgresql+psycopg://`) | psycopg2 | Native async support for later phases, better `COPY` performance for bulk ingest, and it is the maintained line. |
| ORM layer | SQLModel | Raw SQLAlchemy / raw SQL | One class defines both the table and the Pydantic model, so the schema and the API contract cannot silently diverge. Response models remain separate to stop `hashed_password` leaking. |
| Enum storage | `VARCHAR` + Pydantic validation | Native PG `ENUM` | Adding a value to a native enum needs a migration and takes locks. VARCHAR keeps the schema portable to SQLite for tests at zero cost. |
| Auth | JWT (HS256) + bcrypt | Sessions | Stateless: the API scales horizontally without shared session storage, and the dashboard is a separate origin. |
| Test database | SQLite in-memory | Postgres service container | Phase-1 logic is engine-agnostic. The PostgreSQL-specific artefact (BRIN) is verified by a dedicated CI job that runs the real migration against `postgres:17-alpine`. |

## Phase plan

| Phase | Scope |
| --- | --- |
| **1 — skeleton** ✅ | Repo layout, full schema + migration, auth, registry CRUD, SSE plumbing, demo target, Docker, CI. |
| **2 — collection & analytics** ✅ | Proxy forwarding, ingest, prober, rollup job, all `/v1/analytics/*`, real SSE `snapshot` frames. |
| **3 — ML** ✅ | Holt-Winters forecasting, robust z-score + IsolationForest anomaly detection with explanations, NASA dataset seeding, model metrics. |
| **4 — dashboard & deploy** ✅ | React + Recharts live dashboard, nginx image, Kustomize manifests. |

All four are built. What is deliberately *not* here: per-endpoint anomaly
detection (needs an alert-suppression policy first), a persisted model-metrics
table (the store is per-process, see `app/ml/metrics_store.py`), auth on the
analytics read path, and a retention/downsampling policy for `request_log`.
