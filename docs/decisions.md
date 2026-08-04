# Decision log

Ambiguities resolved during implementation, and the reasoning. The rule the
phase-1 brief set was "choose the simpler option, note it here, continue".

---

## D1 — The repository root *is* `pulsegrid/`

**Ambiguity.** The brief's tree is rooted at `pulsegrid/`, but the work happens
in an already-initialised, empty git repository.

**Decision.** Treat the repository root as `pulsegrid/` rather than nesting a
`pulsegrid/` directory inside it.

**Why.** A nested folder would put every path one level below the repo root for
no benefit, and would break `docker compose` / CI working-directory defaults.
Every path in the brief maps 1:1 onto the repo root.

---

## D2 — Login takes JSON and auth uses `HTTPBearer`, not OAuth2 password flow

**Ambiguity.** The brief specifies `POST /v1/auth/login` but not its content
type, and FastAPI's usual idiom (`OAuth2PasswordBearer`) requires a
form-encoded `username`/`password` body.

**Decision.** `POST /v1/auth/login` accepts JSON `{email, password}`; protected
routes use `HTTPBearer`.

**Why.** PulseGrid is a JSON API consumed by a React client. Forcing one
form-encoded endpoint into an otherwise JSON API is a wart, and the field would
have to be called `username` while holding an email. `HTTPBearer` still renders
the Authorize button in Swagger UI, so nothing is lost.

---

## D3 — Registry rows are scoped to their owner

**Ambiguity.** The brief says "CRUD `/v1/apis`, auth required" without saying
whether every authenticated user sees every API.

**Decision.** A `viewer` sees and edits only the APIs it registered; an `admin`
sees the whole fleet. Accessing someone else's API returns **404**, not 403.

**Why.** `owner_user_id` exists in the schema, so leaving it unenforced would
be dead weight. 404-over-403 avoids confirming that another tenant's API id
exists. Total cost: one helper function.

---

## D4 — Enums are stored as `VARCHAR`, not native PostgreSQL `ENUM`

**Ambiguity.** The brief writes "role (str enum: admin | viewer)", which could
mean either.

**Decision.** Plain `VARCHAR` columns, validated by `enum.StrEnum` at the
Pydantic layer.

**Why.** Adding a value to a native PostgreSQL enum requires a migration and
takes locks. VARCHAR costs nothing, keeps the schema portable to SQLite for the
test suite, and the validation still happens — just one layer up.

`enum.StrEnum` specifically (not `class X(str, Enum)`): on Python 3.11+,
`str(member)` on a `(str, Enum)` mixin returns `"UserRole.VIEWER"`, which would
have put a garbage `role` claim into every JWT.

---

## D5 — Tests run on SQLite; migrations are verified on real PostgreSQL

**Ambiguity.** The brief explicitly leaves the choice open and asks for a
justification.

**Decision.** `pytest` runs against SQLite in-memory. A separate CI job runs
`alembic upgrade head` against a real `postgres:17-alpine` service container and
asserts both `request_log` indexes exist.

**Why.** Everything phase 1 tests (auth, registry CRUD, routing, SSE framing) is
engine-agnostic SQL; a container would add ~40s of startup per run for no extra
coverage. The one genuinely PostgreSQL-specific artefact is the BRIN index, and
that is covered directly by the migration job. Phase 2's `date_trunc` rollup
queries *are* engine-specific and will get their own PostgreSQL-backed tests.

---

## D6 — The BRIN index is declared in `models.py` *and* created with raw SQL

**Ambiguity.** The brief mandates the raw-SQL `op.execute(...)` form in the
migration, which leaves the index invisible to `SQLModel.metadata`.

**Decision.** Keep the raw SQL in the migration (as specified) *and* declare
`Index("ix_request_log_time_brin", "time", postgresql_using="brin")` in the
model.

**Why.** Without the model-side declaration, every future `--autogenerate` run
proposes to **drop** the BRIN index, and `alembic check` fails permanently — so
the drift guard in CI would have to be deleted, which is the more valuable
thing. `postgresql_using` is a dialect-scoped keyword that SQLite ignores, so
the test suite is unaffected. Verified: `alembic check` reports no drift.

---

## D7 — `demo-target` ships inside the backend image

**Ambiguity.** The brief allows either `backend/app/demo_target.py` or a
separate `demo-target/` service.

**Decision.** `backend/app/demo_target.py`, run by the compose service with a
different `uvicorn` entrypoint against the same image.

**Why.** One image to build, cache and push instead of two. The module is ~70
lines and has no dependency the backend doesn't already have.

---

## D8 — ML libraries are installed in phase 1

**Ambiguity.** `statsmodels`/`scikit-learn`/`pandas` are in the locked stack but
unused until phase 3.

**Decision.** Install them now, in the main dependency list.

**Why.** It keeps the image and the lockfile stable across phases — phase 3
becomes a pure code change with no rebuild surprise mid-hackathon. Cost is a
one-off increase in image size and first-build time; both are cached afterwards.

---

## D9 — `bcrypt` pinned to `<5.0`

**Decision.** `bcrypt>=4.0,<5.0` alongside `passlib[bcrypt]`.

**Why.** passlib 1.7.4 reads `bcrypt.__about__`, which bcrypt 5 removed. The pin
avoids a noisy-then-fragile code path in the auth hot loop. Revisit if passlib
ships a release that drops the `__about__` probe.

---

## D10 — The proxy registers one route per HTTP verb

**Decision.** Instead of a single `@api_route(methods=[...])`, `/proxy/{path}`
is registered once per verb via `add_api_route` with an explicit `operation_id`.

**Why.** A single multi-method route shares one generated `operationId` across
all verbs, and FastAPI emits a `Duplicate Operation ID` warning while producing
an invalid OpenAPI document. One route per verb also gives client generators
usable method names.

---

## D11 — One extra test file beyond the three listed

**Decision.** Added `tests/test_pipeline.py` alongside the specified
`test_health.py`, `test_auth.py` and `test_registry.py`. It follows one
observation from `POST /v1/ingest` through the rollup to the number the
dashboard renders, and covers endpoint normalisation, rollup idempotency, every
analytics series, the health score, both anomaly detectors, forecasting and
backtesting, and the SSE frame format.

**Why.** Each stage of the pipeline can pass its own unit test while the
handoff between two of them silently drops or mis-buckets rows — a bug class
that only an end-to-end test catches. (This file replaced the phase-1
`test_stubs.py`, which asserted that unimplemented routes returned `501`; those
routes are now implemented, so that contract no longer exists to test.)

---

## D12 — `/health` reports `degraded` when the database is down

**Ambiguity.** The brief specifies `{"status": "ok", "db": "<up|down>"}`, which
does not say what `status` becomes when `db` is `down`.

**Decision.** `status` is `"ok"` only when the ping succeeds, otherwise
`"degraded"`. The healthy response is exactly `{"status":"ok","db":"up",...}`
as specified.

**Why.** A probe that reports `ok` while its only datastore is unreachable is
worse than no probe — Kubernetes would keep routing traffic to it.
