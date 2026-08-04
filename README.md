# PulseGrid

[![CI](https://github.com/Yousuf-beep/Mlops-Hackathon/actions/workflows/ci.yml/badge.svg)](https://github.com/Yousuf-beep/Mlops-Hackathon/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![PostgreSQL 17](https://img.shields.io/badge/postgres-17--alpine-336791.svg)](https://www.postgresql.org/)

> **Point a base URL at PulseGrid and every API call is measured, charted,
> forecast and explained — with no SDK, no code change and no sidecar.**

PulseGrid is an enterprise API analytics and performance-management platform.
It monitors **real, live APIs** through a transparent reverse proxy, computes
Golden-Signal analytics (latency, traffic, errors, saturation), detects
anomalies with ML and explains them in plain English, and forecasts traffic —
all on a single PostgreSQL instance and a single FastAPI process.

> **Status: Phase 1 (skeleton) complete.** The schema, migrations, auth, API
> registry, SSE plumbing, demo upstream, Docker stack and CI pipeline are
> built and verified. Analytics, proxying and ML are declared in OpenAPI and
> return `501 {"detail": "not implemented: <name>"}` until their phase lands.
> See the [API overview](#api-overview) for exactly what is live.

---

## Table of contents

- [Problem statement](#problem-statement)
- [Architecture](#architecture)
- [Tech stack](#tech-stack)
- [Local setup](#local-setup)
- [Try it — end-to-end curl walkthrough](#try-it--end-to-end-curl-walkthrough)
- [API overview](#api-overview)
- [Database design](#database-design)
- [Testing](#testing)
- [CI/CD](#cicd)
- [Repository layout](#repository-layout)
- [Roadmap](#roadmap)
- [Team](#team)
- [License](#license)

---

## Problem statement

Teams running production APIs typically have three badly connected things: an
APM vendor they cannot afford at scale, a metrics stack (Prometheus + Grafana)
that requires instrumenting every service, and a spreadsheet where someone
tracks SLOs by hand.

All three answer *what happened*. None of them answer *why*. None of them tell
you what is about to happen.

PulseGrid collapses the three into one deployable system:

| | Conventional stack | PulseGrid |
| --- | --- | --- |
| **Collection** | Instrument every service with an SDK or sidecar | Repoint one base URL at the proxy — zero code change |
| **Alerting** | Threshold breached | Threshold breached **plus** the expected range, the signal, and a sentence explaining why |
| **Outlook** | Backward-looking dashboards | Traffic forecasts with prediction intervals |
| **Operations** | Prometheus + Grafana + Alertmanager + a TSDB | `docker compose up` |

---

## Architecture

Full detail, including the component table and the rejected alternatives, is in
**[`docs/architecture.md`](docs/architecture.md)**. Every non-obvious
implementation choice is logged in **[`docs/decisions.md`](docs/decisions.md)**.

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

> 📌 *Placeholder: rendered architecture diagram — `docs/img/architecture.png` (phase 4).*

**The central idea.** A monitoring system has two workloads with opposite
shapes: collection is a high-rate stream of small inserts, dashboards are wide
range scans needing millisecond aggregates. Serving both from one table means
every dashboard refresh scans the raw log and gets slower every minute the
system runs. PulseGrid separates them — `request_log` takes the writes,
`metric_rollup` serves the reads, and a background job bridges them once a
minute. Dashboard query cost is then bounded by the *window requested*, not by
total uptime. See [Database design](#database-design).

---

## Tech stack

| Layer | Choice | Why this one |
| --- | --- | --- |
| Language | **Python 3.12** | `enum.StrEnum`, native generics and `datetime.UTC` — the schema and API code read cleanly without `typing` back-compat noise. |
| Web framework | **FastAPI** | Pydantic-native validation, automatic OpenAPI, first-class `StreamingResponse` for SSE, and dependency injection that makes the auth guard three lines. |
| ORM / models | **SQLModel** (Pydantic v2 + SQLAlchemy 2.x) | One class defines both the table and its validation, so schema and API contract cannot silently diverge. Response models stay separate so `hashed_password` can never leak. |
| Database | **PostgreSQL 17** (`postgres:17-alpine`, pinned) | BRIN indexes, `date_trunc`, window functions and `ON CONFLICT` upserts give time-series behaviour with no extra engine. Pinned, never `latest` — index behaviour must not drift between machines. |
| Driver | **psycopg 3** (`postgresql+psycopg://`) | The maintained line; native async for later phases and fast `COPY` for bulk ingest. |
| Migrations | **Alembic** | Versioned, reversible DDL — and the only place the raw-SQL BRIN index can live. CI runs `alembic check` so models and migrations cannot drift. |
| Background jobs | **APScheduler** (in-process) | The jobs are short, idempotent and single-tenant. Celery would add a broker, a worker image and a second deployment for zero gain — and break the one-command deploy. |
| Live updates | **SSE** (`text/event-stream`) | Traffic is strictly server→client. SSE is plain HTTP (survives proxies, no upgrade handshake) and browsers reconnect automatically. WebSockets would add a protocol for nothing. |
| HTTP client | **httpx** | One library for the reverse proxy, the active prober and the test client. |
| Auth | **python-jose** (JWT HS256) + **passlib[bcrypt]** | Stateless tokens scale horizontally with no shared session store; bcrypt is adaptive, salted and GPU-resistant. |
| ML | **statsmodels**, **scikit-learn**, **pandas** | Holt-Winters for forecasting (fits in ms, ships prediction intervals); IsolationForest for multivariate anomalies. Both fit inside the API process — no model server. |
| Frontend | **React + Vite + TypeScript + Recharts** | Vite for instant HMR; Recharts is declarative SVG, so time-series panels are composition rather than imperative canvas code. |
| Dependency mgmt | **uv** | Resolves and installs an order of magnitude faster than pip — it makes the Docker dependency layer cheap to rebuild. |
| Lint / format | **ruff** | Linter and formatter in one binary, fast enough to gate every commit. `E,F,I,UP,B` at line-length 100. |
| Tests | **pytest** | Fixture composition maps naturally onto FastAPI's dependency overrides. |
| CI/CD | **GitHub Actions** → **GHCR** | Lint, test, real-PostgreSQL migration check and image publish, all on one runner with no external service. |

---

## Local setup

**Prerequisites:** Docker Desktop (or Docker Engine + Compose v2). Nothing else
— Python and Node are only needed if you want to run the pieces natively.

```bash
git clone <your-repo-url> pulsegrid && cd pulsegrid
cp .env.example .env
docker compose up --build
```

That's it. Three services come up:

| Service | URL | Purpose |
| --- | --- | --- |
| `api` | <http://localhost:8000> · [docs](http://localhost:8000/docs) | The PulseGrid API. Runs `alembic upgrade head` before binding, so it never serves against an unexpected schema. |
| `db` | `localhost:5432` | PostgreSQL 17, data persisted in the `pulsegrid-pgdata` volume. |
| `demo-target` | <http://localhost:8001> | A synthetic upstream to monitor: `/fast`, `/slow` (100–800 ms), `/flaky` (~10% 500s). |

Verify:

```bash
curl localhost:8000/health          # {"status":"ok","db":"up","version":"0.1.0"}
curl localhost:8001/flaky           # the demo upstream
curl -N localhost:8000/v1/stream    # SSE heartbeats, one every 5s (ctrl-C to stop)
```

<details>
<summary><b>Running the backend natively (no Docker for the API)</b></summary>

```bash
docker compose up -d db             # you still want a real PostgreSQL
cd backend
uv venv && uv pip install -r pyproject.toml --group dev
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

`.env.example` already points `DATABASE_URL` at `localhost:5432` for exactly
this case.
</details>

<details>
<summary><b>Running the dashboard</b></summary>

```bash
cd frontend
npm install
npm run dev                         # http://localhost:5173
```

The API allows CORS from `localhost:5173` out of the box.
</details>

---

## Try it — end-to-end curl walkthrough

The full phase-1 acceptance path: register → log in → register an API → read it
back. Copy-paste as a block.

```bash
# 1 — Register an operator account
curl -s -X POST localhost:8000/v1/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"demo@pulsegrid.dev","password":"pulsegrid-demo-pw"}'
# → {"id":1,"email":"demo@pulsegrid.dev","role":"viewer","created_at":"..."}

# 2 — Log in and capture the JWT
TOKEN=$(curl -s -X POST localhost:8000/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"demo@pulsegrid.dev","password":"pulsegrid-demo-pw"}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# 3 — Register the demo upstream for monitoring
curl -s -X POST localhost:8000/v1/apis \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"name":"Demo Target",
       "base_url":"/proxy/demo",
       "upstream_url":"http://demo-target:8001",
       "slo_target":0.995,
       "slo_latency_ms":300}'
# → 201 {"id":1,"name":"Demo Target",...,"owner_user_id":1,...}

# 4 — List it back
curl -s localhost:8000/v1/apis -H "Authorization: Bearer $TOKEN"
# → [{"id":1,"name":"Demo Target",...}]

# 5 — Confirm the guard rails
curl -s -o /dev/null -w '%{http_code}\n' localhost:8000/v1/apis
# → 401   (no token)
curl -s "localhost:8000/v1/analytics/latency?api_id=1"
# → {"detail":"not implemented: analytics.latency"}   (501, phase 2)
```

On Windows PowerShell, replace the `TOKEN=$(...)` line with:

```powershell
$TOKEN = (curl.exe -s -X POST localhost:8000/v1/auth/login `
  -H 'Content-Type: application/json' `
  -d '{"email":"demo@pulsegrid.dev","password":"pulsegrid-demo-pw"}' | ConvertFrom-Json).access_token
```

---

## API overview

✅ implemented · 🚧 declared in OpenAPI, returns `501 {"detail": "not implemented: <name>"}`

| Method | Route | Auth | Description | Status |
| --- | --- | :---: | --- | :---: |
| `GET` | `/health` | — | Liveness + a real database ping | ✅ |
| `GET` | `/docs` · `/redoc` · `/openapi.json` | — | Interactive API documentation | ✅ |
| `POST` | `/v1/auth/register` | — | Create an operator account | ✅ |
| `POST` | `/v1/auth/login` | — | Exchange credentials for a JWT | ✅ |
| `GET` | `/v1/auth/me` | 🔒 | Return the authenticated account | ✅ |
| `POST` | `/v1/apis` | 🔒 | Register an API for monitoring | ✅ |
| `GET` | `/v1/apis` | 🔒 | List visible APIs (paginated) | ✅ |
| `GET` | `/v1/apis/{api_id}` | 🔒 | Fetch one registered API | ✅ |
| `PATCH` | `/v1/apis/{api_id}` | 🔒 | Partially update a registered API | ✅ |
| `DELETE` | `/v1/apis/{api_id}` | 🔒 | Deregister an API | ✅ |
| `GET` | `/v1/stream` | — | SSE live channel (heartbeat frames) | ✅ |
| `POST` | `/v1/ingest` | — | Bulk-ingest SDK-observed calls | 🚧 phase 2 |
| `*` | `/proxy/{path}` | — | Transparent reverse proxy + measurement | 🚧 phase 2 |
| `GET` | `/v1/analytics/latency` | — | p50/p95/p99/avg latency series | 🚧 phase 2 |
| `GET` | `/v1/analytics/traffic` | — | Requests-per-minute series | 🚧 phase 2 |
| `GET` | `/v1/analytics/errors` | — | Error-rate series | 🚧 phase 2 |
| `GET` | `/v1/analytics/health` | — | Composite 0–100 health score vs SLO | 🚧 phase 2 |
| `GET` | `/v1/analytics/summary` | — | Fleet-wide summary tiles | 🚧 phase 2 |
| `GET` | `/v1/forecast/{api_id}` | — | Traffic forecast with intervals | 🚧 phase 3 |
| `GET` | `/v1/anomalies/{api_id}` | — | Detected anomalies with explanations | 🚧 phase 3 |
| `GET` | `/v1/models/metrics` | — | Offline model evaluation metrics | 🚧 phase 3 |

**Conventions.** Everything lives under `/v1` except `/health` (stable probe
path for orchestrators) and `/proxy/{path}` (must mirror upstream paths
verbatim so callers change nothing but a base URL). Every error — validation,
auth, not-found, not-implemented — uses the same `{"detail": ...}` shape.

**Demo upstream** (port 8001, ✅ fully implemented): `GET /fast`, `GET /slow`
(random 100–800 ms), `GET /flaky` (~10% 500s), `GET /health`.

---

## Database design

Six tables. The design decision that matters is the **raw-log / rollup split**
and the **index strategy** that makes it work on stock PostgreSQL.

> 📌 *Placeholder: entity-relationship diagram — `docs/img/erd.png` (phase 4).*

### Tables

| Table | Purpose | Workload |
| --- | --- | --- |
| `users` | Operator accounts that own registered APIs and read the dashboard | Low volume |
| `api_registry` | Catalogue of monitored APIs, their upstreams and SLO targets | Low volume |
| `request_log` | **Raw append-only request facts** — one row per observed API call | **Write-heavy** |
| `metric_rollup` | **Per-minute Golden-Signal aggregates** — the only table analytics reads | **Read-heavy** |
| `alert` | Fired anomaly / SLO-burn / health alerts, each with its explanation | Low volume |
| `forecast` | Traffic forecast points with prediction intervals | Low volume |

Every table carries a `COMMENT` in the database itself:

```console
$ docker compose exec db psql -U pulsegrid -c "\dt+"
 public | request_log   | table | ... | Raw append-only request facts (write-heavy). BRIN on time +
                                        B-tree on (api_id, time DESC); aggregated into metric_rollup.
 public | metric_rollup | table | ... | Per-minute Golden-Signal aggregates (read-heavy). Serves all
                                        analytics endpoints so dashboards never scan request_log.
```

### Raw log vs rollup separation

`request_log` is the hot write path — the reverse proxy, the ingest endpoint
and the active prober all append to it. `metric_rollup` holds one row per
`(minute bucket, api, endpoint)`, produced once a minute by an APScheduler job
using `date_trunc('minute', time)` GROUP BY queries.

**Every analytics endpoint and every dashboard chart reads only from
`metric_rollup`.** A dashboard refresh therefore reads a few hundred
pre-aggregated rows instead of millions of raw ones, and its cost is bounded by
the *window requested* rather than by total system uptime. That is what gives a
plain PostgreSQL instance the query profile of a time-series database.

### Index strategy

| Table | Index | Type | Reasoning |
| --- | --- | --- | --- |
| `request_log` | `ix_request_log_time_brin (time)` | **BRIN** | The table is append-only, so rows are *already physically ordered by* `time`. BRIN stores one min/max summary per range of disk blocks instead of one entry per row, so a time-range scan skips almost every block that cannot match — at an index size of **kilobytes** rather than the hundreds of megabytes a B-tree would cost at ingest scale. This is the single highest-leverage index in the schema, and it only works *because* the table is append-only. |
| `request_log` | `ix_request_log_api_id_time (api_id, time DESC)` | B-tree | BRIN is block-level, so it cannot answer "the last 15 minutes **for API 3**" selectively. This composite covers exactly that, and `DESC` matches the `ORDER BY … DESC LIMIT n` shape the rollup job and drill-downs issue. |
| `metric_rollup` | `ix_metric_rollup_api_id_bucket (api_id, bucket DESC)` | B-tree | Covers every dashboard window query. |
| `metric_rollup` | `uq_metric_rollup_bucket_api_endpoint (bucket, api_id, endpoint)` | **UNIQUE** | Makes the rollup job idempotent. It re-processes a short trailing window to catch late-arriving rows, so it must `ON CONFLICT … DO UPDATE` rather than duplicate buckets. |
| `users` | `ix_users_email (email)` | UNIQUE | Login lookup. |
| `api_registry` | `ix_api_registry_name`, `ix_api_registry_owner_user_id` | B-tree | Name search and owner scoping. |
| `alert` · `forecast` | `(api_id, fired_at DESC)` · `(api_id, generated_at DESC)` | B-tree | "Recent items for this API" — the only read pattern either table has. |

BRIN has no portable SQLAlchemy spelling, so the migration creates it with raw
SQL, exactly as the design intends:

```python
op.execute("CREATE INDEX ix_request_log_time_brin ON request_log USING BRIN (time);")
```

Verify it on a running stack:

```console
$ docker compose exec db psql -U pulsegrid -c "\d request_log"
Indexes:
    "request_log_pkey" PRIMARY KEY, btree (id)
    "ix_request_log_api_id_time" btree (api_id, "time" DESC)
    "ix_request_log_time_brin" brin ("time")
```

### Other schema decisions

- **Enums are `VARCHAR`, not native PostgreSQL `ENUM`.** Adding a value to a
  native enum requires a migration and takes locks; a `VARCHAR` validated by
  `enum.StrEnum` at the Pydantic layer costs nothing and keeps the schema
  portable to SQLite for tests.
- **All timestamps are `TIMESTAMPTZ`.** Naive local times would make
  cross-region rollups meaningless.
- **`is_error` is denormalised** onto `request_log` so the rollup job can `SUM`
  a boolean instead of re-evaluating a predicate over millions of rows.
- **No drift is possible.** CI runs `alembic check` against a real
  `postgres:17-alpine`; an empty autogenerate diff proves `models.py` and the
  migration still agree.

---

## Testing

```bash
cd backend
uv run pytest              # 35 tests
uv run ruff check .
uv run ruff format --check .
```

| Suite | Covers |
| --- | --- |
| `tests/test_health.py` | `/health` DB ping, `/docs`, and that every router appears in the OpenAPI document |
| `tests/test_auth.py` | Register (incl. duplicate + weak password), login (incl. wrong password and unknown email returning *identical* 401s), token-guarded access, and unit tests for the hashing/JWT primitives |
| `tests/test_registry.py` | Full CRUD happy path, defaults, 404, auth-required on every verb, owner scoping, admin visibility, validation |
| `tests/test_stubs.py` | Every stub returns the agreed `501 {"detail": "not implemented: <name>"}`, and `/v1/stream` emits real SSE frames |

**Why SQLite in-memory?** Everything phase 1 tests — auth, registry CRUD,
routing, SSE framing — is engine-agnostic SQL, so a PostgreSQL container would
add ~40s of startup per run for no extra coverage. The one genuinely
PostgreSQL-specific artefact, the BRIN index, is covered directly by a separate
CI job that runs the real migration against `postgres:17-alpine` and asserts
both `request_log` indexes exist. Phase 2's `date_trunc` rollup queries *are*
engine-specific and will get their own PostgreSQL-backed tests.

---

## CI/CD

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs on every push and
pull request to `main`, with in-progress runs cancelled when superseded.

| Job | What it does |
| --- | --- |
| **lint** | `ruff check .` and `ruff format --check .` |
| **test** | `pytest` against SQLite in-memory |
| **migrate** | Spins up a real `postgres:17-alpine` service, runs `alembic upgrade head`, asserts `ix_request_log_time_brin` **and** `ix_request_log_api_id_time` exist, then runs `alembic check` to prove models and migrations have not drifted |
| **docker** | Needs all three. Builds the backend image with Buildx + GHA layer cache. On **push to `main` only**, logs in with `GITHUB_TOKEN` and pushes to `ghcr.io/yousuf-beep/mlops-hackathon` tagged with the commit `sha` and `latest`. Pull requests build but publish nothing. |

Published images: <https://github.com/Yousuf-beep/Mlops-Hackathon/pkgs/container/Mlops-Hackathon>

---

## Repository layout

```
pulsegrid/
├── backend/
│   ├── app/
│   │   ├── main.py           # app factory, lifespan, /health
│   │   ├── config.py         # pydantic-settings Settings
│   │   ├── database.py       # engine, session dependency, DB ping
│   │   ├── models.py         # all SQLModel tables + index strategy notes
│   │   ├── schemas.py        # request/response models
│   │   ├── demo_target.py    # the synthetic upstream (/fast, /slow, /flaky)
│   │   ├── auth/             # security.py (hashing, JWT), dependencies.py (guards)
│   │   ├── routers/          # auth, registry, ingest, analytics, ml, stream
│   │   ├── jobs/scheduler.py # APScheduler instance + register_jobs()
│   │   └── ml/               # forecasting.py, anomaly.py (signatures, phase 3)
│   ├── alembic/              # env.py + the initial migration
│   ├── tests/                # pytest suite
│   ├── pyproject.toml        # uv-managed deps, ruff + pytest config
│   └── Dockerfile            # multi-stage, non-root
├── frontend/                 # Vite + React + TS + Recharts scaffold
├── k8s/                      # manifests — phase 4
├── notebooks/                # ML exploration — phase 3
├── scripts/seed_nasa.py      # NASA-HTTP dataset loader — phase 3
├── docs/
│   ├── architecture.md       # full architecture + rejected alternatives
│   └── decisions.md          # every judgement call, with reasoning
├── .github/workflows/ci.yml
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## Roadmap

| Phase | Scope | Status |
| --- | --- | :---: |
| **1 — Skeleton** | Repo layout, complete schema + migration, auth, registry CRUD, SSE plumbing, demo upstream, Docker stack, CI | ✅ |
| **2 — Collection & analytics** | Reverse-proxy forwarding, `/v1/ingest`, active prober, rollup job, all `/v1/analytics/*`, real SSE metric frames | ⏳ |
| **3 — ML** | Holt-Winters forecasting, robust z-score + IsolationForest anomaly detection with explanations, NASA dataset seeding, model metrics | ⏳ |
| **4 — Dashboard & deploy** | React + Recharts dashboard, Kubernetes manifests, ERD and architecture diagrams | ⏳ |

---

## Team

| Name | Role | GitHub |
| --- | --- | --- |
| *TBD* | Backend, database, ML | [@handle](https://github.com/) |
| *TBD* | Frontend, infrastructure, CI/CD | [@handle](https://github.com/) |

---

## License

[MIT](LICENSE) © 2026 The PulseGrid Team
