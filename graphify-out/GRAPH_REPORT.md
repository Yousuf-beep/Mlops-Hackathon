# Graph Report - .  (2026-08-04)

## Corpus Check
- Corpus is ~18,709 words - fits in a single context window. You may not need a graph.

## Summary
- 556 nodes · 1070 edges · 29 communities (23 shown, 6 thin omitted)
- Extraction: 70% EXTRACTED · 30% INFERRED · 0% AMBIGUOUS · INFERRED: 326 edges (avg confidence: 0.53)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_API Wire Contracts|API Wire Contracts]]
- [[_COMMUNITY_Registry & User Models|Registry & User Models]]
- [[_COMMUNITY_Password & JWT Primitives|Password & JWT Primitives]]
- [[_COMMUNITY_Settings & DB Session Layer|Settings & DB Session Layer]]
- [[_COMMUNITY_Schema, Migrations & Index Strategy|Schema, Migrations & Index Strategy]]
- [[_COMMUNITY_Analytics Endpoint Contracts|Analytics Endpoint Contracts]]
- [[_COMMUNITY_Frontend Shell & Golden Signals|Frontend Shell & Golden Signals]]
- [[_COMMUNITY_CICD & Container Stack|CI/CD & Container Stack]]
- [[_COMMUNITY_ML Endpoint Contracts|ML Endpoint Contracts]]
- [[_COMMUNITY_Frontend Dependencies|Frontend Dependencies]]
- [[_COMMUNITY_Demo Upstream Service|Demo Upstream Service]]
- [[_COMMUNITY_Anomaly Detection Design|Anomaly Detection Design]]
- [[_COMMUNITY_Registry CRUD Tests|Registry CRUD Tests]]
- [[_COMMUNITY_Test Fixtures & SQLite Strategy|Test Fixtures & SQLite Strategy]]
- [[_COMMUNITY_TypeScript App Config|TypeScript App Config]]
- [[_COMMUNITY_Traffic Forecasting Design|Traffic Forecasting Design]]
- [[_COMMUNITY_TypeScript Node Config|TypeScript Node Config]]
- [[_COMMUNITY_Stub & SSE Contract Tests|Stub & SSE Contract Tests]]
- [[_COMMUNITY_NASA Dataset Seeder|NASA Dataset Seeder]]
- [[_COMMUNITY_Health & OpenAPI Tests|Health & OpenAPI Tests]]
- [[_COMMUNITY_Frontend Lint Rules|Frontend Lint Rules]]
- [[_COMMUNITY_TypeScript Project Refs|TypeScript Project Refs]]
- [[_COMMUNITY_Backend Package Root|Backend Package Root]]
- [[_COMMUNITY_Auth Package Root|Auth Package Root]]
- [[_COMMUNITY_Jobs Package Root|Jobs Package Root]]
- [[_COMMUNITY_ML Package Root|ML Package Root]]
- [[_COMMUNITY_Test Package Root|Test Package Root]]

## God Nodes (most connected - your core abstractions)
1. `UserRole` - 44 edges
2. `User` - 34 edges
3. `ErrorResponse` - 26 edges
4. `AlertType` - 24 edges
5. `AlertSeverity` - 23 edges
6. `CurrentUser` - 22 edges
7. `ApiCreate` - 18 edges
8. `ApiUpdate` - 18 edges
9. `ApiRead` - 18 edges
10. `compilerOptions` - 18 edges

## Surprising Connections (you probably didn't know these)
- `enum.StrEnum: (str, Enum) would put 'UserRole.VIEWER' in the JWT` --rationale_for--> `UserRole`  [EXTRACTED]
  docs/decisions.md → backend/app/models.py
- `NASA-HTTP access-log dataset (1995, ~3.4M requests)` --shares_data_with--> `RequestLog`  [EXTRACTED]
  README.md → backend/app/models.py
- `bcrypt pinned <5.0 (passlib reads bcrypt.__about__)` --rationale_for--> `hash_password()`  [EXTRACTED]
  docs/decisions.md → backend/app/auth/security.py
- `enum.StrEnum: (str, Enum) would put 'UserRole.VIEWER' in the JWT` --rationale_for--> `create_access_token()`  [EXTRACTED]
  docs/decisions.md → backend/app/auth/security.py
- `/health reports 'degraded' when the database is down` --rationale_for--> `check_connection()`  [EXTRACTED]
  docs/decisions.md → backend/app/database.py

## Import Cycles
- 1-file cycle: `backend/app/models.py -> backend/app/models.py`
- 1-file cycle: `backend/app/main.py -> backend/app/main.py`
- 1-file cycle: `backend/tests/conftest.py -> backend/tests/conftest.py`

## Hyperedges (group relationships)
- **Time-series strategy on plain PostgreSQL** — raw_log_rollup_split, brin_index_strategy, composite_btree_strategy, rollup_idempotency, date_trunc_rollup, app_models_requestlog, app_models_metricrollup, rejected_tsdb [EXTRACTED 1.00]
- **Phase-1 verification chain (lint, test, migrate, publish)** — ci_lint_job, ci_test_job, ci_migrate_job, ci_docker_job, alembic_drift_guard, sqlite_test_strategy, ghcr_publish [EXTRACTED 1.00]
- **One-command deployability (why no broker, no TSDB, no second image)** — apscheduler_over_celery, rejected_tsdb, demo_target_in_backend_image, svc_db, svc_api, svc_demo_target, migrate_before_bind [INFERRED 0.85]

## Communities (29 total, 6 thin omitted)

### Community 0 - "API Wire Contracts"
Cohesion: 0.08
Nodes (55): AlertSeverity, AlertType, Category of a fired :class:`Alert`., Operator-facing severity of a fired :class:`Alert`., ErrorResponse, ForecastPoint, HealthResponse, IngestAccepted (+47 more)

### Community 1 - "Registry & User Models"
Cohesion: 0.12
Nodes (52): ApiCreate, ApiRegistry, ApiUpdate, ApiRegistry, A PulseGrid operator account.      Attributes:         id: Surrogate primary, A live API that PulseGrid monitors.      ``base_url`` is the address PulseGrid, Role granted to a PulseGrid user., User (+44 more)

### Community 2 - "Password & JWT Primitives"
Cohesion: 0.06
Nodes (42): Any, create_access_token(), decode_token(), hash_password(), Pure security primitives: password hashing and JWT encode/decode.  This module, Hash a plaintext password with bcrypt.      Args:         password: The plain, Verify a plaintext password against a stored digest.      Args:         plain, Issue a signed JWT access token.      Args:         subject: The user id the (+34 more)

### Community 3 - "Settings & DB Session Layer"
Cohesion: 0.06
Nodes (39): get_settings(), Application configuration.  All runtime configuration is read from environment v, Typed application settings loaded from the environment.      Attributes:, Return the process-wide settings singleton.      Cached so that the ``.env`` fil, Settings, check_connection(), create_db_and_tables(), _engine_options() (+31 more)

### Community 4 - "Schema, Migrations & Index Strategy"
Cohesion: 0.08
Nodes (35): alembic check as a model/migration drift guard, Alembic runtime environment.  The database URL is read from :class:`app.config.S, Emit SQL to stdout without connecting (``alembic upgrade --sql``)., Connect to the database and run migrations in a transaction., run_migrations_offline(), run_migrations_online(), Alert, Forecast (+27 more)

### Community 5 - "Analytics Endpoint Contracts"
Cohesion: 0.14
Nodes (32): ApiIdParam, HealthScoreResponse, A named series over a time window, read from ``metric_rollup``., Composite health score for one API., Fleet-wide summary tiles for the dashboard header., SummaryResponse, TimeseriesResponse, Query (+24 more)

### Community 6 - "Frontend Shell & Golden Signals"
Cohesion: 0.09
Nodes (26): description, ge, int, le, object, Query, Request, str (+18 more)

### Community 7 - "CI/CD & Container Stack"
Cohesion: 0.11
Nodes (22): LogSource, How a :class:`RequestLog` row was observed., CI job: docker (build, publish to GHCR on main only), CI job: lint (ruff check + format), CI job: migrate (real postgres:17-alpine, asserts indexes), CI job: test (pytest on SQLite), .github/workflows/ci.yml, GHCR publish with GITHUB_TOKEN, sha + latest tags (+14 more)

### Community 8 - "ML Endpoint Contracts"
Cohesion: 0.21
Nodes (22): AnomalyRead, ApiIdPath, AnomalyRead, ForecastResponse, ModelMetrics, Traffic forecast for one API., A detected anomaly, surfaced as an explained alert., Offline evaluation metrics for the deployed ML models. (+14 more)

### Community 9 - "Frontend Dependencies"
Cohesion: 0.09
Nodes (22): dependencies, react, react-dom, recharts, description, devDependencies, oxlint, @types/node (+14 more)

### Community 10 - "Demo Upstream Service"
Cohesion: 0.11
Nodes (20): EchoResponse, fast(), flaky(), health(), A tiny, deliberately imperfect upstream API for PulseGrid to monitor.  Run with, Standard demo-target reply., Return immediately so compose can health-check the service.      Returns:, Respond instantly.      Returns:         EchoResponse: A zero-latency reply. (+12 more)

### Community 11 - "Anomaly Detection Design"
Cohesion: 0.12
Nodes (20): DataFrame, float, int, object, Series, str, IsolationForest over joint Golden-Signal features, AnomalyResult (+12 more)

### Community 12 - "Registry CRUD Tests"
Cohesion: 0.17
Nodes (20): object, str, TestClient, _create_api(), Tests for the ``/v1/apis`` registry CRUD routes., An administrator lists APIs owned by other accounts., An availability target above 1.0 is rejected by schema validation., Create an API and return its serialised body.      Args:         client: HTTP cl (+12 more)

### Community 13 - "Test Fixtures & SQLite Strategy"
Cohesion: 0.15
Nodes (19): FastAPI, object, Session, str, TestClient, User, admin_user_fixture(), app_fixture() (+11 more)

### Community 14 - "TypeScript App Config"
Cohesion: 0.10
Nodes (19): compilerOptions, allowArbitraryExtensions, allowImportingTsExtensions, erasableSyntaxOnly, jsx, lib, module, moduleDetection (+11 more)

### Community 15 - "Traffic Forecasting Design"
Cohesion: 0.17
Nodes (16): DataFrame, float, int, Series, str, Holt-Winters exponential smoothing for traffic forecasting, backtest(), build_series() (+8 more)

### Community 16 - "TypeScript Node Config"
Cohesion: 0.12
Nodes (16): compilerOptions, allowImportingTsExtensions, erasableSyntaxOnly, lib, module, moduleDetection, noEmit, noFallthroughCasesInSwitch (+8 more)

### Community 17 - "Stub & SSE Contract Tests"
Cohesion: 0.24
Nodes (9): str, TestClient, Contract tests for the phase-1 stubs and the SSE heartbeat stream.  These lock i, Each stub returns 501 with the agreed ``not implemented: <name>`` detail., ``POST /v1/ingest`` validates its body, then reports 501., ``/v1/stream`` returns bounded ``heartbeat`` frames in SSE wire format., test_ingest_stub_returns_501(), test_stream_emits_sse_heartbeats() (+1 more)

### Community 18 - "NASA Dataset Seeder"
Cohesion: 0.25
Nodes (8): ArgumentParser, NASA-HTTP access-log dataset (1995, ~3.4M requests), build_parser(), main(), int, str, Construct the command-line parser.      Returns:         argparse.ArgumentParser, Entry point.      Args:         argv: Argument vector, defaulting to ``sys.argv[

### Community 19 - "Health & OpenAPI Tests"
Cohesion: 0.28
Nodes (8): TestClient, Tests for the ``/health`` probe and the generated OpenAPI document., Every phase-1 route group is present in the OpenAPI document., The Swagger UI page is reachable at ``/docs``., ``/health`` returns ``ok``/``up`` when the database answers a ping., test_docs_ui_is_served(), test_health_reports_ok_when_database_is_reachable(), test_openapi_document_lists_every_router()

### Community 20 - "Frontend Lint Rules"
Cohesion: 0.33
Nodes (5): plugins, rules, react/only-export-components, react/rules-of-hooks, $schema

## Knowledge Gaps
- **86 isolated node(s):** `bool`, `int`, `timedelta`, `Any`, `str` (+81 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **6 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `datetime` connect `Schema, Migrations & Index Strategy` to `API Wire Contracts`, `Password & JWT Primitives`, `Settings & DB Session Layer`, `Frontend Shell & Golden Signals`, `Traffic Forecasting Design`?**
  _High betweenness centrality (0.095) - this node is a cross-community bridge._
- **Why does `MetricRollup` connect `Schema, Migrations & Index Strategy` to `Anomaly Detection Design`, `Analytics Endpoint Contracts`, `Traffic Forecasting Design`?**
  _High betweenness centrality (0.071) - this node is a cross-community bridge._
- **Why does `UserRole` connect `Registry & User Models` to `API Wire Contracts`, `Password & JWT Primitives`, `Schema, Migrations & Index Strategy`, `Analytics Endpoint Contracts`, `CI/CD & Container Stack`, `ML Endpoint Contracts`?**
  _High betweenness centrality (0.061) - this node is a cross-community bridge._
- **Are the 39 inferred relationships involving `UserRole` (e.g. with `ApiCreate` and `ApiRegistry`) actually correct?**
  _`UserRole` has 39 INFERRED edges - model-reasoned connections that need verification._
- **Are the 31 inferred relationships involving `User` (e.g. with `ApiCreate` and `ApiRegistry`) actually correct?**
  _`User` has 31 INFERRED edges - model-reasoned connections that need verification._
- **Are the 23 inferred relationships involving `ErrorResponse` (e.g. with `ApiCreate` and `ApiRegistry`) actually correct?**
  _`ErrorResponse` has 23 INFERRED edges - model-reasoned connections that need verification._
- **Are the 20 inferred relationships involving `AlertType` (e.g. with `AnomalyRead` and `ApiCreate`) actually correct?**
  _`AlertType` has 20 INFERRED edges - model-reasoned connections that need verification._