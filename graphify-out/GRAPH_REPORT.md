# Graph Report - Mlops-Hackathon  (2026-08-04)

## Corpus Check
- 58 files · ~37,313 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 975 nodes · 2431 edges · 38 communities (30 shown, 8 thin omitted)
- Extraction: 63% EXTRACTED · 37% INFERRED · 0% AMBIGUOUS · INFERRED: 896 edges (avg confidence: 0.53)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `ff936bbc`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]

## God Nodes (most connected - your core abstractions)
1. `ApiRegistry` - 93 edges
2. `ErrorResponse` - 71 edges
3. `UserRole` - 52 edges
4. `Alert` - 52 edges
5. `MetricRollup` - 41 edges
6. `RequestLog` - 40 edges
7. `User` - 38 edges
8. `HealthScoreResponse` - 37 edges
9. `SummaryResponse` - 37 edges
10. `AlertType` - 35 edges

## Surprising Connections (you probably didn't know these)
- `/health reports 'degraded' when the database is down` --rationale_for--> `create_app()`  [EXTRACTED]
  docs/decisions.md → backend/app/main.py
- `enum.StrEnum: (str, Enum) would put 'UserRole.VIEWER' in the JWT` --rationale_for--> `UserRole`  [EXTRACTED]
  docs/decisions.md → backend/app/models.py
- `BRIN declared in models AND raw SQL, to keep alembic check honest` --rationale_for--> `RequestLog`  [EXTRACTED]
  docs/decisions.md → backend/app/models.py
- `Denormalised is_error for cheap SUM in rollups` --rationale_for--> `RequestLog`  [EXTRACTED]
  README.md → backend/app/models.py
- `bcrypt pinned <5.0 (passlib reads bcrypt.__about__)` --rationale_for--> `hash_password()`  [EXTRACTED]
  docs/decisions.md → backend/app/auth/security.py

## Import Cycles
- 1-file cycle: `backend/app/analytics.py -> backend/app/analytics.py`
- 1-file cycle: `backend/app/models.py -> backend/app/models.py`
- 1-file cycle: `backend/app/main.py -> backend/app/main.py`
- 1-file cycle: `backend/app/jobs/rollup.py -> backend/app/jobs/rollup.py`
- 1-file cycle: `scripts/seed_nasa.py -> scripts/seed_nasa.py`
- 1-file cycle: `backend/tests/conftest.py -> backend/tests/conftest.py`

## Hyperedges (group relationships)
- **Time-series strategy on plain PostgreSQL** — raw_log_rollup_split, brin_index_strategy, composite_btree_strategy, rollup_idempotency, date_trunc_rollup, app_models_requestlog, app_models_metricrollup, rejected_tsdb [EXTRACTED 1.00]
- **Phase-1 verification chain (lint, test, migrate, publish)** — ci_lint_job, ci_test_job, ci_migrate_job, ci_docker_job, alembic_drift_guard, sqlite_test_strategy, ghcr_publish [EXTRACTED 1.00]
- **One-command deployability (why no broker, no TSDB, no second image)** — apscheduler_over_celery, rejected_tsdb, demo_target_in_backend_image, svc_db, svc_api, svc_demo_target, migrate_before_bind [INFERRED 0.85]

## Communities (38 total, 8 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.06
Nodes (79): ApiRegistry, LogSource, A live API that PulseGrid monitors.      ``base_url`` is the address PulseGrid, One observed API call — the raw, append-only time-series fact table.      This, How a :class:`RequestLog` row was observed., RequestLog, IngestAccepted, IngestEvent (+71 more)

### Community 1 - "Community 1"
Cohesion: 0.06
Nodes (97): AnomalyResult, ApiCreate, ApiRegistry, ApiUpdate, bootstrap(), ensure_admin(), Return the demo operator account, creating it if absent.      Args:         sess, Register the bundled demo endpoints if the registry is empty.      Args: (+89 more)

### Community 2 - "Community 2"
Cohesion: 0.06
Nodes (41): Any, create_access_token(), decode_token(), hash_password(), Pure security primitives: password hashing and JWT encode/decode.  This module, Hash a plaintext password with bcrypt.      Args:         password: The plain, Verify a plaintext password against a stored digest.      Args:         plain, Issue a signed JWT access token.      Args:         subject: The user id the (+33 more)

### Community 3 - "Community 3"
Cohesion: 0.18
Nodes (12): create_app(), lifespan(), FastAPI application factory and lifespan wiring.  Run with ``uvicorn app.main:ap, Manage startup and shutdown of process-wide resources.      Starts APScheduler o, Manage startup and shutdown of process-wide resources.      Provisions demo data, Build and configure the FastAPI application.      Returns:         FastAPI: The, Build and configure the FastAPI application.      Returns:         FastAPI: The, FastAPI (+4 more)

### Community 4 - "Community 4"
Cohesion: 0.09
Nodes (56): ApiOverviewItem, _aggregate(), api_health(), api_overview(), endpoint_breakdown(), error_series(), fleet_summary(), health_score() (+48 more)

### Community 5 - "Community 5"
Cohesion: 0.10
Nodes (64): ApiIdParam, EndpointBreakdownResponse, ErrorResponse, HealthScoreResponse, OverviewResponse, A named series over a time window, read from ``metric_rollup``., Composite health score for one API., Fleet-wide summary tiles for the dashboard header. (+56 more)

### Community 6 - "Community 6"
Cohesion: 0.06
Nodes (69): datetime, float, int, Session, object, Session, str, TestClient (+61 more)

### Community 7 - "Community 7"
Cohesion: 0.06
Nodes (41): alembic check as a model/migration drift guard, FastAPI, object, Session, str, TestClient, User, BRIN declared in models AND raw SQL, to keep alembic check honest (+33 more)

### Community 8 - "Community 8"
Cohesion: 0.06
Nodes (80): AnomalyRead, ApiIdPath, Alert, Forecast, A fired alert with a human-readable explanation.      ``explanation`` is delib, A stored traffic forecast point with its prediction interval.      Attributes:, AnomalyRead, ForecastPoint (+72 more)

### Community 9 - "Community 9"
Cohesion: 0.09
Nodes (22): dependencies, react, react-dom, recharts, description, devDependencies, oxlint, @types/node (+14 more)

### Community 10 - "Community 10"
Cohesion: 0.08
Nodes (28): EchoResponse, fast(), flaky(), health(), A tiny, deliberately imperfect upstream API for PulseGrid to monitor.  Run with, Standard demo-target reply., Return immediately so compose can health-check the service.      Returns:, Respond instantly.      Returns:         EchoResponse: A zero-latency reply. (+20 more)

### Community 11 - "Community 11"
Cohesion: 0.07
Nodes (50): Alert, int, Session, DataFrame, float, int, object, Series (+42 more)

### Community 12 - "Community 12"
Cohesion: 0.17
Nodes (20): object, str, TestClient, _create_api(), Tests for the ``/v1/apis`` registry CRUD routes., An administrator lists APIs owned by other accounts., An availability target above 1.0 is rejected by schema validation., Create an API and return its serialised body.      Args:         client: HTTP cl (+12 more)

### Community 13 - "Community 13"
Cohesion: 0.10
Nodes (20): API overview, Architecture, CI/CD, Dashboard, Database design, Index strategy, License, Local setup (+12 more)

### Community 14 - "Community 14"
Cohesion: 0.10
Nodes (19): compilerOptions, allowArbitraryExtensions, allowImportingTsExtensions, erasableSyntaxOnly, jsx, lib, module, moduleDetection (+11 more)

### Community 15 - "Community 15"
Cohesion: 0.09
Nodes (32): DataFrame, float, int, Series, str, Holt-Winters exponential smoothing for traffic forecasting, ML libraries installed in phase 1 to freeze the image, backtest() (+24 more)

### Community 16 - "Community 16"
Cohesion: 0.12
Nodes (16): compilerOptions, allowImportingTsExtensions, erasableSyntaxOnly, lib, module, moduleDetection, noEmit, noFallthroughCasesInSwitch (+8 more)

### Community 17 - "Community 17"
Cohesion: 0.20
Nodes (9): First-boot provisioning so a fresh stack is immediately alive.  A monitoring pla, Application configuration.  All runtime configuration is read from environment v, create_db_and_tables(), Database engine, session factory and FastAPI session dependency.  A single modul, Create every table declared on ``SQLModel.metadata``.      Only used for local t, FastAPI authentication dependencies.  PulseGrid uses a plain ``Authorization: Be, Active prober: synthetically exercise every registered API on a schedule.  Passi, psycopg 3 (postgresql+psycopg://) over psycopg2 (+1 more)

### Community 18 - "Community 18"
Cohesion: 0.14
Nodes (13): D10 — The proxy registers one route per HTTP verb, D11 — One extra test file beyond the three listed, D12 — `/health` reports `degraded` when the database is down, D1 — The repository root *is* `pulsegrid/`, D2 — Login takes JSON and auth uses `HTTPBearer`, not OAuth2 password flow, D3 — Registry rows are scoped to their owner, D4 — Enums are stored as `VARCHAR`, not native PostgreSQL `ENUM`, D5 — Tests run on SQLite; migrations are verified on real PostgreSQL (+5 more)

### Community 19 - "Community 19"
Cohesion: 0.28
Nodes (8): TestClient, Tests for the ``/health`` probe and the generated OpenAPI document., Every phase-1 route group is present in the OpenAPI document., The Swagger UI page is reachable at ``/docs``., ``/health`` returns ``ok``/``up`` when the database answers a ping., test_docs_ui_is_served(), test_health_reports_ok_when_database_is_reachable(), test_openapi_document_lists_every_router()

### Community 20 - "Community 20"
Cohesion: 0.33
Nodes (5): plugins, rules, react/only-export-components, react/rules-of-hooks, $schema

### Community 22 - "Community 22"
Cohesion: 0.05
Nodes (69): axes(), ErrorChart(), ErrorChartProps, LatencyChart(), LatencyChartProps, mergeSeries(), Row, tooltipContent() (+61 more)

### Community 29 - "Community 29"
Cohesion: 0.18
Nodes (12): APScheduler in-process over Celery+broker, BackgroundScheduler, heartbeat_job(), APScheduler wiring for PulseGrid's periodic work.  Why APScheduler and not Cel, Register jobs and start the scheduler, honouring ``SCHEDULER_ENABLED``.      R, Log a liveness line so scheduler failures are visible in the API logs.      Th, Log a liveness line so scheduler failures are visible in the API logs.      Ke, Register every periodic job on the scheduler.      Idempotent: ``replace_exist (+4 more)

### Community 30 - "Community 30"
Cohesion: 0.22
Nodes (8): Components, Data flow, Key technology decisions, One-line pitch, Phase plan, Problem statement, PulseGrid — Architecture, Time-series strategy on plain PostgreSQL

### Community 31 - "Community 31"
Cohesion: 0.29
Nodes (7): SQLModel table definitions — the complete PulseGrid schema.  Time-series strat, Return the current time as a timezone-aware UTC datetime.      Returns:, utcnow(), datetime, Separate response models so hashed_password cannot leak, SQLModel: one class for table + validation, TIMESTAMPTZ for every timestamp

### Community 32 - "Community 32"
Cohesion: 0.29
Nodes (7): check_connection(), get_session(), Yield a request-scoped database session.      Used as a FastAPI dependency (``De, Ping the database with a trivial query.      Args:         session: The session, bool, Session, /health reports 'degraded' when the database is down

### Community 33 - "Community 33"
Cohesion: 0.33
Nodes (5): Alembic runtime environment.  The database URL is read from :class:`app.config.S, Emit SQL to stdout without connecting (``alembic upgrade --sql``)., Connect to the database and run migrations in a transaction., run_migrations_offline(), run_migrations_online()

### Community 34 - "Community 34"
Cohesion: 0.33
Nodes (6): get_settings(), Typed application settings loaded from the environment.      Attributes:, Return the process-wide settings singleton.      Cached so that the ``.env`` fil, Return the process-wide settings singleton.      Cached so that the ``.env`` fil, Settings, BaseSettings

### Community 35 - "Community 35"
Cohesion: 0.40
Nodes (4): Apply, Decisions worth knowing, Kubernetes manifests, What is in here

### Community 36 - "Community 36"
Cohesion: 0.50
Nodes (4): _engine_options(), Pick engine options appropriate for the target dialect.      SQLite (used by the, object, str

## Knowledge Gaps
- **133 isolated node(s):** `bool`, `int`, `Any`, `str`, `object` (+128 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **8 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ApiRegistry` connect `Community 0` to `Community 1`, `Community 4`, `Community 5`, `Community 8`, `Community 11`, `Community 17`, `Community 31`?**
  _High betweenness centrality (0.158) - this node is a cross-community bridge._
- **Why does `Client` connect `Community 0` to `Community 22`?**
  _High betweenness centrality (0.131) - this node is a cross-community bridge._
- **Why does `MetricRollup` connect `Community 4` to `Community 0`, `Community 1`, `Community 5`, `Community 6`, `Community 11`, `Community 15`, `Community 17`, `Community 31`?**
  _High betweenness centrality (0.055) - this node is a cross-community bridge._
- **Are the 89 inferred relationships involving `ApiRegistry` (e.g. with `AnomalyResult` and `ApiCreate`) actually correct?**
  _`ApiRegistry` has 89 INFERRED edges - model-reasoned connections that need verification._
- **Are the 67 inferred relationships involving `ErrorResponse` (e.g. with `ApiCreate` and `ApiIdParam`) actually correct?**
  _`ErrorResponse` has 67 INFERRED edges - model-reasoned connections that need verification._
- **Are the 47 inferred relationships involving `UserRole` (e.g. with `ApiCreate` and `ApiRegistry`) actually correct?**
  _`UserRole` has 47 INFERRED edges - model-reasoned connections that need verification._
- **Are the 48 inferred relationships involving `Alert` (e.g. with `AnomalyResult` and `ApiIdPath`) actually correct?**
  _`Alert` has 48 INFERRED edges - model-reasoned connections that need verification._