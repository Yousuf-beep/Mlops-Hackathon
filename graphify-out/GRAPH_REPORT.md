# Graph Report - Mlops-Hackathon  (2026-08-05)

## Corpus Check
- 77 files · ~68,029 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1529 nodes · 3789 edges · 75 communities (65 shown, 10 thin omitted)
- Extraction: 67% EXTRACTED · 33% INFERRED · 0% AMBIGUOUS · INFERRED: 1235 edges (avg confidence: 0.53)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `882cacf5`
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
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 54|Community 54]]
- [[_COMMUNITY_Community 55|Community 55]]
- [[_COMMUNITY_Community 56|Community 56]]
- [[_COMMUNITY_Community 57|Community 57]]
- [[_COMMUNITY_Community 58|Community 58]]
- [[_COMMUNITY_Community 59|Community 59]]
- [[_COMMUNITY_Community 60|Community 60]]
- [[_COMMUNITY_Community 61|Community 61]]
- [[_COMMUNITY_Community 62|Community 62]]
- [[_COMMUNITY_Community 63|Community 63]]
- [[_COMMUNITY_Community 64|Community 64]]
- [[_COMMUNITY_Community 65|Community 65]]
- [[_COMMUNITY_Community 66|Community 66]]
- [[_COMMUNITY_Community 67|Community 67]]
- [[_COMMUNITY_Community 68|Community 68]]
- [[_COMMUNITY_Community 69|Community 69]]
- [[_COMMUNITY_Community 70|Community 70]]
- [[_COMMUNITY_Community 71|Community 71]]
- [[_COMMUNITY_Community 72|Community 72]]
- [[_COMMUNITY_Community 73|Community 73]]
- [[_COMMUNITY_Community 74|Community 74]]

## God Nodes (most connected - your core abstractions)
1. `ApiRegistry` - 108 edges
2. `ErrorResponse` - 77 edges
3. `UserRole` - 63 edges
4. `Alert` - 58 edges
5. `AnomalyRead` - 50 edges
6. `MetricRollup` - 49 edges
7. `AlertType` - 46 edges
8. `AlertSeverity` - 45 edges
9. `HealthScoreResponse` - 44 edges
10. `SummaryResponse` - 44 edges

## Surprising Connections (you probably didn't know these)
- `CORS allowance for the Vite dev origin` --rationale_for--> `create_app()`  [EXTRACTED]
  frontend/README.md → backend/app/main.py
- `enum.StrEnum: (str, Enum) would put 'UserRole.VIEWER' in the JWT` --rationale_for--> `UserRole`  [EXTRACTED]
  docs/decisions.md → backend/app/models.py
- `BRIN declared in models AND raw SQL, to keep alembic check honest` --rationale_for--> `RequestLog`  [EXTRACTED]
  docs/decisions.md → backend/app/models.py
- `Denormalised is_error for cheap SUM in rollups` --rationale_for--> `RequestLog`  [EXTRACTED]
  README.md → backend/app/models.py
- `NASA-HTTP access-log dataset (1995, ~3.4M requests)` --shares_data_with--> `RequestLog`  [EXTRACTED]
  README.md → backend/app/models.py

## Import Cycles
- 1-file cycle: `backend/app/analytics.py -> backend/app/analytics.py`
- 1-file cycle: `backend/app/models.py -> backend/app/models.py`
- 1-file cycle: `backend/app/main.py -> backend/app/main.py`
- 1-file cycle: `backend/app/infra/discovery.py -> backend/app/infra/discovery.py`
- 1-file cycle: `backend/app/jobs/rollup.py -> backend/app/jobs/rollup.py`
- 1-file cycle: `scripts/seed_nasa.py -> scripts/seed_nasa.py`
- 1-file cycle: `backend/tests/conftest.py -> backend/tests/conftest.py`

## Hyperedges (group relationships)
- **Time-series strategy on plain PostgreSQL** — raw_log_rollup_split, brin_index_strategy, composite_btree_strategy, rollup_idempotency, date_trunc_rollup, app_models_requestlog, app_models_metricrollup, rejected_tsdb [EXTRACTED 1.00]
- **Phase-1 verification chain (lint, test, migrate, publish)** — ci_lint_job, ci_test_job, ci_migrate_job, ci_docker_job, alembic_drift_guard, sqlite_test_strategy, ghcr_publish [EXTRACTED 1.00]
- **One-command deployability (why no broker, no TSDB, no second image)** — apscheduler_over_celery, rejected_tsdb, demo_target_in_backend_image, svc_db, svc_api, svc_demo_target, migrate_before_bind [INFERRED 0.85]

## Communities (75 total, 10 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.14
Nodes (24): NASA-HTTP access-log dataset (1995, ~3.4M requests), Path, Random, build_parser(), build_rescaler(), main(), open_log(), parse_lines() (+16 more)

### Community 1 - "Community 1"
Cohesion: 0.18
Nodes (36): ApiCreate, ApiRegistry, ApiUpdate, Role granted to a PulseGrid user., Role granted to a PulseGrid user., UserRole, ApiCreate, ApiRead (+28 more)

### Community 2 - "Community 2"
Cohesion: 0.09
Nodes (25): Any, create_access_token(), decode_token(), hash_password(), Hash a plaintext password with bcrypt.      Args:         password: The plain, Verify a plaintext password against a stored digest.      Args:         plain, Issue a signed JWT access token.      Args:         subject: The user id the, Decode and validate a JWT access token.      Args:         token: The encoded (+17 more)

### Community 3 - "Community 3"
Cohesion: 0.20
Nodes (12): bootstrap(), ensure_admin(), Run first-boot provisioning, honouring ``DEMO_AUTOSEED``.      Failures are logg, Return the demo operator account, creating it if absent.      Args:         sess, Return the demo operator account, creating it if absent.      Args:         sess, Register the bundled demo endpoints if the registry is empty.      Args:, Register the bundled demo endpoints if the registry is empty.      Args:, Run first-boot provisioning, honouring ``DEMO_AUTOSEED``.      Failures are logg (+4 more)

### Community 4 - "Community 4"
Cohesion: 0.11
Nodes (35): SlaGauge(), Stage(), App(), clock, compact(), millis(), percent(), STATUS_LABEL (+27 more)

### Community 5 - "Community 5"
Cohesion: 0.06
Nodes (133): AnomalyResult, ApiIdParam, ApiOverviewItem, AlertSeverity, AlertType, ApiRegistry, MetricRollup, Category of a fired :class:`Alert`. (+125 more)

### Community 6 - "Community 6"
Cohesion: 0.27
Nodes (6): A slug that matches no registered API is a 404, not a 501 or a 500., A slug that matches no registered API is a 404, not a 501 or a 500., The registry stays authenticated even though analytics is open., The registry stays authenticated even though analytics is open., test_proxy_returns_404_for_unmounted_slug(), test_registered_apis_are_not_exposed_without_a_token()

### Community 7 - "Community 7"
Cohesion: 0.67
Nodes (3): load_rollups(), Read one API's recent rollups into a DataFrame.      Args:         session: Acti, Read one API's recent rollups into a DataFrame.      Args:         session: Acti

### Community 8 - "Community 8"
Cohesion: 0.12
Nodes (43): AnomalyRead, ApiIdPath, Forecast, A stored traffic forecast point with its prediction interval.      Attributes:, A stored traffic forecast point with its prediction interval.      Attributes:, ForecastPoint, ForecastResponse, ModelMetrics (+35 more)

### Community 9 - "Community 9"
Cohesion: 0.08
Nodes (24): dependencies, motion, react, react-dom, react-router-dom, recharts, description, devDependencies (+16 more)

### Community 10 - "Community 10"
Cohesion: 0.05
Nodes (43): EchoResponse, fast(), flaky(), get_user(), health(), A tiny, deliberately imperfect upstream API for PulseGrid to monitor.  Run with, Fail with a 500 roughly one call in ten.      Args:         response: Injected s, Return a synthetic user, or 404 outside the valid id range.      Exists so each (+35 more)

### Community 11 - "Community 11"
Cohesion: 0.67
Nodes (3): Return the current dirty-counter value.      Returns:         int: Monotonically, version(), int

### Community 12 - "Community 12"
Cohesion: 0.17
Nodes (20): object, str, TestClient, _create_api(), Tests for the ``/v1/apis`` registry CRUD routes., An administrator lists APIs owned by other accounts., An availability target above 1.0 is rejected by schema validation., Create an API and return its serialised body.      Args:         client: HTTP cl (+12 more)

### Community 13 - "Community 13"
Cohesion: 0.09
Nodes (21): API overview, Architecture, CI/CD, Dashboard, Database design, Index strategy, License, Local setup (+13 more)

### Community 14 - "Community 14"
Cohesion: 0.10
Nodes (19): compilerOptions, allowArbitraryExtensions, allowImportingTsExtensions, erasableSyntaxOnly, jsx, lib, module, moduleDetection (+11 more)

### Community 15 - "Community 15"
Cohesion: 0.06
Nodes (46): mark_dirty(), Signal that fresh data is available for the next snapshot.      Called after eve, DataFrame, float, int, Series, str, Holt-Winters exponential smoothing for traffic forecasting (+38 more)

### Community 16 - "Community 16"
Cohesion: 0.12
Nodes (16): compilerOptions, allowImportingTsExtensions, erasableSyntaxOnly, lib, module, moduleDetection, noEmit, noFallthroughCasesInSwitch (+8 more)

### Community 17 - "Community 17"
Cohesion: 0.06
Nodes (81): ContainerPort, ContainerRead, EnvironmentGroup, InfraSnapshot, One port a container exposes, published to the host or not., A published port rendered as an address a person can use., One container, as the dashboard shows it., A browsable endpoint, filed under the environment it belongs to. (+73 more)

### Community 18 - "Community 18"
Cohesion: 0.14
Nodes (13): D10 — The proxy registers one route per HTTP verb, D11 — One extra test file beyond the three listed, D12 — `/health` reports `degraded` when the database is down, D1 — The repository root *is* `pulsegrid/`, D2 — Login takes JSON and auth uses `HTTPBearer`, not OAuth2 password flow, D3 — Registry rows are scoped to their owner, D4 — Enums are stored as `VARCHAR`, not native PostgreSQL `ENUM`, D5 — Tests run on SQLite; migrations are verified on real PostgreSQL (+5 more)

### Community 19 - "Community 19"
Cohesion: 0.24
Nodes (9): TestClient, Tests for the ``/health`` probe and the generated OpenAPI document., Every phase-1 route group is present in the OpenAPI document., The Swagger UI page is reachable at ``/docs``., The Swagger UI page is reachable at ``/docs``., ``/health`` returns ``ok``/``up`` when the database answers a ping., test_docs_ui_is_served(), test_health_reports_ok_when_database_is_reachable() (+1 more)

### Community 20 - "Community 20"
Cohesion: 0.33
Nodes (5): plugins, rules, react/only-export-components, react/rules-of-hooks, $schema

### Community 22 - "Community 22"
Cohesion: 0.07
Nodes (34): AlertFeed(), AlertFeedProps, ApiList(), ApiListProps, EndpointRankingProps, EndpointTable(), EndpointTableProps, ModelPanel() (+26 more)

### Community 29 - "Community 29"
Cohesion: 0.18
Nodes (12): APScheduler in-process over Celery+broker, BackgroundScheduler, heartbeat_job(), APScheduler wiring for PulseGrid's periodic work.  Why APScheduler and not Cel, Register jobs and start the scheduler, honouring ``SCHEDULER_ENABLED``.      R, Log a liveness line so scheduler failures are visible in the API logs.      Th, Log a liveness line so scheduler failures are visible in the API logs.      Ke, Register every periodic job on the scheduler.      Idempotent: ``replace_exist (+4 more)

### Community 30 - "Community 30"
Cohesion: 0.22
Nodes (8): Components, Data flow, Key technology decisions, One-line pitch, Phase plan, Problem statement, PulseGrid — Architecture, Time-series strategy on plain PostgreSQL

### Community 31 - "Community 31"
Cohesion: 0.07
Nodes (35): Alembic runtime environment.  The database URL is read from :class:`app.config.S, Emit SQL to stdout without connecting (``alembic upgrade --sql``)., Connect to the database and run migrations in a transaction., run_migrations_offline(), run_migrations_online(), First-boot provisioning so a fresh stack is immediately alive.  A monitoring pla, Application configuration.  All runtime configuration is read from environment v, create_db_and_tables() (+27 more)

### Community 32 - "Community 32"
Cohesion: 0.16
Nodes (16): alembic check as a model/migration drift guard, BRIN declared in models AND raw SQL, to keep alembic check honest, CI job: docker (build, publish to GHCR on main only), CI job: lint (ruff check + format), CI job: migrate (real postgres:17-alpine, asserts indexes), CI job: test (pytest on SQLite), .github/workflows/ci.yml, GHCR publish with GITHUB_TOKEN, sha + latest tags (+8 more)

### Community 33 - "Community 33"
Cohesion: 0.08
Nodes (51): _aggregate(), anomaly_reads(), api_health(), api_overview(), endpoint_breakdown(), error_series(), fleet_summary(), health_score() (+43 more)

### Community 34 - "Community 34"
Cohesion: 0.25
Nodes (8): get_settings(), Return the process-wide settings singleton.      Cached so that the ``.env`` fil, Return the process-wide settings singleton.      Cached so that the ``.env`` fil, Typed application settings loaded from the environment.      Attributes:, Return the process-wide settings singleton.      Cached so that the ``.env`` fil, Return the process-wide settings singleton.      Cached so that the ``.env`` fil, Settings, BaseSettings

### Community 35 - "Community 35"
Cohesion: 0.25
Nodes (7): Apply, Decisions worth knowing, Kubernetes manifests, Layout: one base, three environments, What differs between the three, What is in `base/`, What is in here

### Community 36 - "Community 36"
Cohesion: 0.50
Nodes (4): _engine_options(), Pick engine options appropriate for the target dialect.      SQLite (used by the, object, str

### Community 38 - "Community 38"
Cohesion: 0.10
Nodes (33): RegisterApiForm(), RegisterApiFormProps, SignInForm(), SignInFormProps, useProof(), ApiError, createApi(), errorDetail() (+25 more)

### Community 39 - "Community 39"
Cohesion: 0.07
Nodes (35): Client, AuthPanel(), LoginPage(), Mode, Proof, PROOF_LABEL, ProofState, ScrambleOptions (+27 more)

### Community 40 - "Community 40"
Cohesion: 0.14
Nodes (25): axes(), binHeatmap(), ErrorChart(), ErrorChartProps, HealthTimelineChart(), HealthTimelineChartProps, HeatmapChart(), HeatmapChartProps (+17 more)

### Community 41 - "Community 41"
Cohesion: 0.15
Nodes (19): FastAPI, object, Session, str, TestClient, User, admin_user_fixture(), app_fixture() (+11 more)

### Community 42 - "Community 42"
Cohesion: 0.11
Nodes (20): Score every registered API's newest bucket and record the findings.      Args:, Score every registered API's newest bucket and record the findings.      Args:, run_anomaly_detection(), A minute with no rows is zero traffic, not a missing observation., A minute with no rows is zero traffic, not a missing observation., A latency cliff in the newest bucket is reported with an expected band., A latency cliff in the newest bucket is reported with an expected band., Too little history means no detection, rather than a false alarm. (+12 more)

### Community 43 - "Community 43"
Cohesion: 0.07
Nodes (41): DataFrame, float, int, object, Series, str, IsolationForest over joint Golden-Signal features, _band() (+33 more)

### Community 44 - "Community 44"
Cohesion: 0.13
Nodes (21): datetime, float, int, Session, as_utc(), compute_rollups(), minute_bucket(), percentile() (+13 more)

### Community 45 - "Community 45"
Cohesion: 0.11
Nodes (41): LogSource, How a :class:`RequestLog` row was observed., One observed API call — the raw, append-only time-series fact table.      This, One observed API call — the raw, append-only time-series fact table.      This i, How a :class:`RequestLog` row was observed., RequestLog, IngestAccepted, IngestEvent (+33 more)

### Community 46 - "Community 46"
Cohesion: 0.33
Nodes (6): Derive the proxy mount slug from a registry row's ``base_url``.      ``base_url`, Derive the proxy mount slug from a registry row's ``base_url``.      ``base_url`, registry_slug(), The proxy mount point is derived from loosely-formatted base URLs., The proxy mount point is derived from loosely-formatted base URLs., test_registry_slug_is_tolerant_of_base_url_shape()

### Community 47 - "Community 47"
Cohesion: 0.31
Nodes (9): ApiRegistry, int, Session, probe_all(), probe_api(), prober_job(), Issue one probe against a registered API and record the result.      Args:, Probe every registered API once.      Args:         session: Active database ses (+1 more)

### Community 48 - "Community 48"
Cohesion: 0.07
Nodes (39): _inspect(), Tests for runtime infrastructure discovery.  The Docker Engine is stubbed rather, Docker's nine-digit fractional seconds are truncated, not rejected., ``0001-01-01T00:00:00Z`` means "never", and must not render as a date., A port bound on IPv4 *and* IPv6 is one address, not two., An internal-only port is still a port; it just has no host address., The load generator publishes nothing, and that is not an error., Every published port gets its own address, ordered by container port. (+31 more)

### Community 49 - "Community 49"
Cohesion: 0.33
Nodes (6): normalise_endpoint(), Fold a concrete request path into a route template.      Args:         path: The, Fold a concrete request path into a route template.      Args:         path: The, Concrete ids collapse to templates so rollups group by route., Concrete ids collapse to templates so rollups group by route., test_normalise_endpoint_folds_identifiers()

### Community 50 - "Community 50"
Cohesion: 0.22
Nodes (10): Append-only physical time ordering (BRIN precondition), Query cost bounded by window, not by uptime, BRIN index on request_log.time, Composite B-tree (api_id, time DESC), date_trunc('minute', time) GROUP BY rollup job, Denormalised is_error for cheap SUM in rollups, Two opposing workloads: insert stream vs range scan, Raw-log / rollup separation (+2 more)

### Community 51 - "Community 51"
Cohesion: 0.07
Nodes (39): ContainerTable(), ContainerTableProps, EMPTY_HINTS, EndpointLink(), noEndpointReason(), say(), uptimeOf(), WebEnvironments() (+31 more)

### Community 52 - "Community 52"
Cohesion: 0.22
Nodes (8): Accessibility & Inclusion, Anti-references, Brand Personality, Design Principles, Product, Product Purpose, Register, Users

### Community 53 - "Community 53"
Cohesion: 0.29
Nodes (5): options, pickTarget(), TARGETS, TOTAL_WEIGHT, traffic()

### Community 54 - "Community 54"
Cohesion: 0.08
Nodes (56): object, Session, str, TestClient, api_fixture(), End-to-end tests for the collection → rollup → analytics → ML pipeline.  These f, Accepted events land in ``request_log`` with normalised endpoints., Accepted events land in ``request_log`` with normalised endpoints. (+48 more)

### Community 55 - "Community 55"
Cohesion: 0.17
Nodes (12): check_connection(), get_session(), Yield a request-scoped database session.      Used as a FastAPI dependency (``De, Ping the database with a trivial query.      Args:         session: The session, create_app(), Build and configure the FastAPI application.      Returns:         FastAPI: The, Build and configure the FastAPI application.      Returns:         FastAPI: The, Build and configure the FastAPI application.      Returns:         FastAPI: The (+4 more)

### Community 56 - "Community 56"
Cohesion: 0.11
Nodes (34): Alert, A fired alert with a human-readable explanation.      ``explanation`` is delib, A fired alert with a human-readable explanation.      ``explanation`` is deliber, AnomalyRead, A detected anomaly, surfaced as an explained alert., A detected anomaly, surfaced as an explained alert., A detected anomaly, surfaced as an explained alert., description (+26 more)

### Community 57 - "Community 57"
Cohesion: 0.40
Nodes (4): downgrade(), Add the nullable ``alert.confidence`` column., Drop ``alert.confidence``., upgrade()

### Community 58 - "Community 58"
Cohesion: 0.15
Nodes (25): Registration payload for ``POST /v1/auth/register``., Credentials payload for ``POST /v1/auth/login``., Public projection of a user. Never contains the password digest., Bearer token envelope returned by ``POST /v1/auth/login``., Token, UserCreate, UserLogin, UserRead (+17 more)

### Community 59 - "Community 59"
Cohesion: 0.10
Nodes (22): Exception, ConnectError, _Answering, _endpoint(), _Raising, A client whose requests all succeed., A client whose requests all fail the same way., A lone browsable endpoint to probe. (+14 more)

### Community 60 - "Community 60"
Cohesion: 0.19
Nodes (17): object, TestClient, MonkeyPatch, _isolate_discovery(), Point discovery at a stub engine., The snapshot carries both projections of one discovery pass., A missing socket yields an explained empty panel, never a 5xx., A stopped service is shown as stopped, not omitted — and sorted last. (+9 more)

### Community 61 - "Community 61"
Cohesion: 0.16
Nodes (16): TestClient, Tests for registration, login and token-guarded access., ``/v1/auth/me`` rejects missing, malformed and wrong-scheme credentials., Registration returns 201 and never echoes the password or its digest., A second registration with the same email returns 409., Passwords shorter than the 8-character minimum are rejected by validation., Correct credentials yield a bearer token that identifies the caller., A wrong password returns 401 with the generic message. (+8 more)

### Community 62 - "Community 62"
Cohesion: 0.25
Nodes (14): A PulseGrid operator account.      Attributes:         id: Surrogate primary, A PulseGrid operator account.      Attributes:         id: Surrogate primary key, User, get_current_user(), Resolve the authenticated user from the ``Authorization`` header.      Args:, Raised when a token is malformed, expired or fails signature checks., TokenError, Session (+6 more)

### Community 63 - "Community 63"
Cohesion: 0.26
Nodes (8): Any, bool, str, DockerEngine, Issue a GET against the Engine and return the decoded JSON body.          Args:, List containers known to the daemon.          Args:             include_stopped:, Fetch the full inspect payload for one container.          The summary from :met, Lazily-connected handle on the Docker Engine API.      One client is shared proc

### Community 64 - "Community 64"
Cohesion: 0.50
Nodes (3): One proxy route per HTTP verb for distinct operationIds, HTTP routers.  Every router is mounted under ``/v1`` except the reverse proxy (`, /v1 prefix except /health and /proxy/{path}

### Community 65 - "Community 65"
Cohesion: 0.23
Nodes (9): Any, bool, str, A leading slash is added, a trailing one removed, and "/" means none., Environment is read from the most deliberate signal available., Stands in for the shared Docker Engine handle., _StubEngine, test_environment_classification() (+1 more)

### Community 66 - "Community 66"
Cohesion: 0.25
Nodes (7): AsyncClient, _build_client(), A minimal async client for the Docker Engine HTTP API.  The Engine speaks plain, Return the shared client, building it on first use., Best guess at the ID of the container this process is running in.      Docker se, Construct a client bound to the configured Docker endpoint.      Understands the, self_container_id()

### Community 67 - "Community 67"
Cohesion: 0.29
Nodes (7): lifespan(), Manage startup and shutdown of process-wide resources.      Starts APScheduler o, Manage startup and shutdown of process-wide resources.      Provisions demo data, Manage startup and shutdown of process-wide resources.      Provisions demo data, Stop the scheduler, waiting for any in-flight job to finish., Stop the scheduler, waiting for any in-flight job to finish., shutdown_scheduler()

### Community 68 - "Community 68"
Cohesion: 0.29
Nodes (7): float, ModelMetrics, str, Record the latest evaluation of one model.      Args:         model_name: Identi, Return the latest metrics for every model that has reported.      Returns:, record(), snapshot()

### Community 69 - "Community 69"
Cohesion: 0.29
Nodes (6): alembic upgrade head runs before uvicorn binds, downgrade(), Initial PulseGrid schema: registry, raw request log, rollups, alerts, forecasts., Drop every PulseGrid table and index, in reverse dependency order., Create every PulseGrid table and index., upgrade()

### Community 70 - "Community 70"
Cohesion: 0.27
Nodes (6): An event for an unregistered API fails loudly instead of orphaning rows., An event for an unregistered API fails loudly instead of orphaning rows., A perfect window scores 100; SLO breaches pull the score down., A perfect window scores 100; SLO breaches pull the score down., test_health_score_penalises_breaches(), test_ingest_rejects_unknown_api()

### Community 71 - "Community 71"
Cohesion: 0.40
Nodes (5): ModelMetrics, model_metrics(), Return the last recorded evaluation metrics per model.      Returns:         lis, Return the last recorded evaluation metrics per model.      Returns:         lis, Return a traffic forecast with 95% prediction intervals.      Args:         api_

### Community 72 - "Community 72"
Cohesion: 0.50
Nodes (3): close_engine(), Close the shared client, if one was ever opened., Release the shared Engine client. Called from the app's lifespan.

## Knowledge Gaps
- **180 isolated node(s):** `bool`, `int`, `Any`, `str`, `object` (+175 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **10 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Client` connect `Community 39` to `Community 45`, `Community 5`, `Community 47`?**
  _High betweenness centrality (0.209) - this node is a cross-community bridge._
- **Why does `ApiRegistry` connect `Community 5` to `Community 0`, `Community 1`, `Community 33`, `Community 3`, `Community 39`, `Community 8`, `Community 45`, `Community 47`, `Community 54`, `Community 58`, `Community 31`?**
  _High betweenness centrality (0.181) - this node is a cross-community bridge._
- **Why does `MetricRollup` connect `Community 5` to `Community 33`, `Community 42`, `Community 43`, `Community 44`, `Community 45`, `Community 15`, `Community 50`, `Community 54`, `Community 31`?**
  _High betweenness centrality (0.047) - this node is a cross-community bridge._
- **Are the 103 inferred relationships involving `ApiRegistry` (e.g. with `AnomalyResult` and `ApiCreate`) actually correct?**
  _`ApiRegistry` has 103 INFERRED edges - model-reasoned connections that need verification._
- **Are the 71 inferred relationships involving `ErrorResponse` (e.g. with `ApiCreate` and `ApiIdParam`) actually correct?**
  _`ErrorResponse` has 71 INFERRED edges - model-reasoned connections that need verification._
- **Are the 57 inferred relationships involving `UserRole` (e.g. with `ApiCreate` and `ApiRegistry`) actually correct?**
  _`UserRole` has 57 INFERRED edges - model-reasoned connections that need verification._
- **Are the 53 inferred relationships involving `Alert` (e.g. with `AnomalyResult` and `ApiIdPath`) actually correct?**
  _`Alert` has 53 INFERRED edges - model-reasoned connections that need verification._