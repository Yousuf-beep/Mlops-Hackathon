"""SQLModel table definitions — the complete PulseGrid schema.

Time-series strategy on plain PostgreSQL
----------------------------------------
PulseGrid deliberately splits its time-series data into two tables:

* ``request_log`` — the **write-heavy** raw record, one row per observed API
  call. It is append-only and naturally ordered by ``time``.
* ``metric_rollup`` — the **read-heavy** pre-aggregated table, one row per
  ``(minute bucket, api, endpoint)``, produced by an APScheduler job using
  ``date_trunc('minute', time)`` GROUP BY queries.

Analytics endpoints and the dashboard read *only* from ``metric_rollup``, so a
dashboard query never scans raw rows. This gives us the query profile of a
time-series database without leaving standard PostgreSQL.

Index strategy (see the initial Alembic migration for the DDL):

* ``request_log.time`` → **BRIN**. BRIN stores min/max summaries per block
  range rather than a pointer per row. Because the table is append-only and
  physically ordered by ``time``, the summaries are extremely tight, so range
  scans are fast while the index costs a few kilobytes instead of the hundreds
  of megabytes a B-tree would cost at ingest scale.
* ``request_log (api_id, time DESC)`` → **B-tree**. Serves the "last N minutes
  for one API" access pattern that BRIN alone cannot answer selectively.
* ``metric_rollup (api_id, bucket DESC)`` → **B-tree**. Serves every dashboard
  window query.
* ``metric_rollup (bucket, api_id, endpoint)`` → **UNIQUE**. Makes the rollup
  job idempotent: re-running it upserts instead of duplicating buckets.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlmodel import Field, SQLModel

# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


def utcnow() -> datetime:
    """Return the current time as a timezone-aware UTC datetime.

    Returns:
        datetime: Now, in UTC. Every timestamp column in PulseGrid is
        ``TIMESTAMPTZ``; storing naive local times would make cross-region
        rollups meaningless.
    """
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    """Return ``value`` as a timezone-aware UTC datetime.

    SQLite has no ``timestamptz``, so values round-trip as naive even though
    they were written by :func:`utcnow`. Treating a naive value as already UTC
    matches how it was written, and lets code that mixes freshly computed
    ``utcnow()`` values with values read back from either engine compare them
    without raising ``TypeError: can't compare offset-naive and
    offset-aware datetimes``.

    Args:
        value: A timestamp, naive or aware.

    Returns:
        datetime: The same instant, tagged UTC.
    """
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


# --------------------------------------------------------------------------- #
# Enumerations (stored as plain VARCHAR, not native PostgreSQL ENUM types)      #
# --------------------------------------------------------------------------- #


class UserRole(StrEnum):
    """Role granted to a PulseGrid user."""

    ADMIN = "admin"
    VIEWER = "viewer"


class LogSource(StrEnum):
    """How a :class:`RequestLog` row was observed."""

    PROXY = "proxy"
    SDK = "sdk"
    PROBE = "probe"


class AlertType(StrEnum):
    """Category of a fired :class:`Alert`."""

    ANOMALY = "anomaly"
    BURN_RATE = "burn_rate"
    HEALTH = "health"


class AlertSeverity(StrEnum):
    """Operator-facing severity of a fired :class:`Alert`."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


# --------------------------------------------------------------------------- #
# Tables                                                                       #
# --------------------------------------------------------------------------- #


class User(SQLModel, table=True):
    """A PulseGrid operator account.

    Attributes:
        id: Surrogate primary key.
        email: Login identity; unique and indexed for the login lookup.
        hashed_password: bcrypt digest — the plaintext is never persisted.
        role: ``admin`` sees every registered API, ``viewer`` sees its own.
        created_at: Account creation timestamp (UTC).
    """

    __tablename__ = "users"
    __table_args__ = {
        "comment": "Operator accounts that own registered APIs and read the dashboard."
    }

    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(sa_column=Column(String(320), nullable=False, unique=True, index=True))
    hashed_password: str = Field(sa_column=Column(String(255), nullable=False))
    role: UserRole = Field(
        default=UserRole.VIEWER,
        sa_column=Column(String(16), nullable=False, server_default=UserRole.VIEWER.value),
    )
    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )


class ApiRegistry(SQLModel, table=True):
    """A live API that PulseGrid monitors.

    ``base_url`` is the address PulseGrid exposes to callers, ``upstream_url``
    is the real service the reverse proxy forwards to. The SLO fields drive the
    error-budget burn-rate alerts added in a later phase.

    Attributes:
        id: Surrogate primary key.
        name: Human-readable label shown on the dashboard.
        base_url: Public-facing path/URL served by the PulseGrid proxy.
        upstream_url: Real upstream origin the proxy forwards to.
        owner_user_id: FK to :class:`User` — the account that registered it.
        auth_type: Free-form hint (``none``, ``bearer``, ``api_key``, ...).
        slo_target: Availability objective as a ratio, e.g. ``0.99``.
        slo_latency_ms: Latency objective in milliseconds.
        created_at: Registration timestamp (UTC).
    """

    __tablename__ = "api_registry"
    __table_args__ = {
        "comment": "Catalogue of monitored APIs, their upstreams and their SLO targets."
    }

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(sa_column=Column(String(128), nullable=False, index=True))
    base_url: str = Field(sa_column=Column(String(512), nullable=False))
    upstream_url: str = Field(sa_column=Column(String(512), nullable=False))
    owner_user_id: int = Field(foreign_key="users.id", nullable=False, index=True)
    auth_type: str | None = Field(default=None, sa_column=Column(String(32), nullable=True))
    slo_target: float = Field(
        default=0.99, sa_column=Column(Float, nullable=False, server_default=text("0.99"))
    )
    slo_latency_ms: int = Field(
        default=500, sa_column=Column(Integer, nullable=False, server_default=text("500"))
    )
    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )


class RequestLog(SQLModel, table=True):
    """One observed API call — the raw, append-only time-series fact table.

    This is the hot write path: the reverse proxy, the ingest endpoint and the
    active prober all append here. Nothing reads it directly on the dashboard
    path; the rollup job aggregates it into :class:`MetricRollup`.

    Attributes:
        id: Surrogate primary key.
        time: When the call completed (UTC, ``TIMESTAMPTZ``). BRIN-indexed.
        api_id: FK to :class:`ApiRegistry`.
        endpoint: Normalised route template, e.g. ``/users/{id}``.
        method: HTTP verb.
        status_code: HTTP response status.
        latency_ms: End-to-end duration in milliseconds.
        request_bytes: Request payload size, when known.
        response_bytes: Response payload size, when known.
        client_ip: Caller address, when known.
        is_error: Denormalised ``status_code >= 500`` (or transport failure) so
            the rollup job can ``SUM`` instead of re-evaluating a predicate.
        source: Which collector produced the row.
    """

    __tablename__ = "request_log"
    __table_args__ = (
        # BRIN over append-only, time-ordered data: block-range summaries
        # instead of one entry per row. The DDL is also written out as raw SQL
        # in the initial migration; declaring it here as well keeps
        # `alembic check` honest instead of proposing to drop it forever.
        # `postgresql_using` is ignored by SQLite, which the test suite uses.
        Index("ix_request_log_time_brin", "time", postgresql_using="brin"),
        # Per-API recent-window queries ("last 15 minutes for API 3").
        Index("ix_request_log_api_id_time", "api_id", text("time DESC")),
        {
            "comment": (
                "Raw append-only request facts (write-heavy). BRIN on time + "
                "B-tree on (api_id, time DESC); aggregated into metric_rollup."
            )
        },
    )

    id: int | None = Field(default=None, primary_key=True)
    time: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    api_id: int = Field(foreign_key="api_registry.id", nullable=False)
    endpoint: str = Field(sa_column=Column(String(512), nullable=False))
    method: str = Field(sa_column=Column(String(10), nullable=False))
    status_code: int = Field(sa_column=Column(Integer, nullable=False))
    latency_ms: float = Field(sa_column=Column(Float, nullable=False))
    request_bytes: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    response_bytes: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    client_ip: str | None = Field(default=None, sa_column=Column(String(45), nullable=True))
    is_error: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default=text("false")),
    )
    source: LogSource = Field(
        default=LogSource.PROXY,
        sa_column=Column(String(16), nullable=False, server_default=LogSource.PROXY.value),
    )


class MetricRollup(SQLModel, table=True):
    """Pre-aggregated per-minute Golden-Signal metrics — the read path.

    One row per ``(bucket, api_id, endpoint)``. The unique constraint makes the
    rollup job idempotent (upsert on conflict), which matters because the job
    re-processes a small trailing window to catch late-arriving rows.

    Attributes:
        id: Surrogate primary key.
        bucket: Minute bucket from ``date_trunc('minute', request_log.time)``.
        api_id: FK to :class:`ApiRegistry`.
        endpoint: Normalised route template the bucket covers.
        req_count: Traffic signal — requests in the bucket.
        err_count: Error signal — errored requests in the bucket.
        p50_ms: Latency signal — median.
        p95_ms: Latency signal — 95th percentile.
        p99_ms: Latency signal — 99th percentile.
        avg_ms: Latency signal — arithmetic mean.
        saturation_pct: Saturation signal, when the upstream reports it.
    """

    __tablename__ = "metric_rollup"
    __table_args__ = (
        UniqueConstraint(
            "bucket", "api_id", "endpoint", name="uq_metric_rollup_bucket_api_endpoint"
        ),
        # Every dashboard window query is "this API, most recent buckets first".
        Index("ix_metric_rollup_api_id_bucket", "api_id", text("bucket DESC")),
        {
            "comment": (
                "Per-minute Golden-Signal aggregates (read-heavy). Serves all "
                "analytics endpoints so dashboards never scan request_log."
            )
        },
    )

    id: int | None = Field(default=None, primary_key=True)
    bucket: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    api_id: int = Field(foreign_key="api_registry.id", nullable=False)
    endpoint: str = Field(sa_column=Column(String(512), nullable=False))
    req_count: int = Field(
        default=0, sa_column=Column(Integer, nullable=False, server_default=text("0"))
    )
    err_count: int = Field(
        default=0, sa_column=Column(Integer, nullable=False, server_default=text("0"))
    )
    p50_ms: float = Field(
        default=0.0, sa_column=Column(Float, nullable=False, server_default=text("0"))
    )
    p95_ms: float = Field(
        default=0.0, sa_column=Column(Float, nullable=False, server_default=text("0"))
    )
    p99_ms: float = Field(
        default=0.0, sa_column=Column(Float, nullable=False, server_default=text("0"))
    )
    avg_ms: float = Field(
        default=0.0, sa_column=Column(Float, nullable=False, server_default=text("0"))
    )
    saturation_pct: float | None = Field(default=None, sa_column=Column(Float, nullable=True))


class Alert(SQLModel, table=True):
    """A fired alert with a human-readable explanation.

    ``explanation`` is deliberately free text: the ML phase writes a sentence
    such as *"p95 latency 812 ms is 4.1σ above the 30-minute baseline"* so the
    dashboard can show *why* an alert fired, not just that it did.

    Attributes:
        id: Surrogate primary key.
        api_id: FK to :class:`ApiRegistry`.
        endpoint: Endpoint the alert concerns, or ``None`` for API-wide.
        type: ``anomaly``, ``burn_rate`` or ``health``.
        severity: ``info``, ``warning`` or ``critical``.
        signal: Golden Signal involved (``latency``/``traffic``/``errors``/
            ``saturation``).
        explanation: Why the alert fired, in plain English.
        metric_value: The observed value that triggered it.
        expected_range: Rendered expected band, e.g. ``"120-180 ms"``.
        confidence: 0-1 heuristic confidence from the detector that fired,
            see :func:`app.ml.anomaly.confidence_from_score`. ``None`` for
            alert types that do not come from the ML detectors.
        fired_at: When the alert was raised (UTC).
        resolved_at: When it cleared, or ``None`` while still firing.
    """

    __tablename__ = "alert"
    __table_args__ = (
        Index("ix_alert_api_id_fired_at", "api_id", text("fired_at DESC")),
        {"comment": "Fired anomaly / SLO-burn / health alerts with their explanations."},
    )

    id: int | None = Field(default=None, primary_key=True)
    api_id: int = Field(foreign_key="api_registry.id", nullable=False)
    endpoint: str | None = Field(default=None, sa_column=Column(String(512), nullable=True))
    type: AlertType = Field(sa_column=Column("type", String(16), nullable=False))
    severity: AlertSeverity = Field(
        default=AlertSeverity.WARNING,
        sa_column=Column(String(16), nullable=False, server_default=AlertSeverity.WARNING.value),
    )
    signal: str = Field(sa_column=Column(String(32), nullable=False))
    explanation: str = Field(sa_column=Column(Text, nullable=False))
    metric_value: float = Field(sa_column=Column(Float, nullable=False))
    expected_range: str = Field(sa_column=Column(String(64), nullable=False))
    confidence: float | None = Field(default=None, sa_column=Column(Float, nullable=True))
    fired_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    resolved_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )


class Forecast(SQLModel, table=True):
    """A stored traffic forecast point with its prediction interval.

    Attributes:
        id: Surrogate primary key.
        api_id: FK to :class:`ApiRegistry`.
        endpoint: Endpoint forecast, or ``None`` for API-wide traffic.
        generated_at: When the forecasting job produced this point (UTC).
        horizon_min: Minutes ahead of ``generated_at`` this point predicts.
        yhat: Point prediction (requests per minute).
        yhat_lower: Lower bound of the prediction interval.
        yhat_upper: Upper bound of the prediction interval.
    """

    __tablename__ = "forecast"
    __table_args__ = (
        Index("ix_forecast_api_id_generated_at", "api_id", text("generated_at DESC")),
        {"comment": "Traffic forecast points with prediction intervals, written by the ML job."},
    )

    id: int | None = Field(default=None, primary_key=True)
    api_id: int = Field(foreign_key="api_registry.id", nullable=False)
    endpoint: str | None = Field(default=None, sa_column=Column(String(512), nullable=True))
    generated_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    horizon_min: int = Field(sa_column=Column(Integer, nullable=False))
    yhat: float = Field(sa_column=Column(Float, nullable=False))
    yhat_lower: float = Field(sa_column=Column(Float, nullable=False))
    yhat_upper: float = Field(sa_column=Column(Float, nullable=False))


__all__ = [
    "Alert",
    "AlertSeverity",
    "AlertType",
    "ApiRegistry",
    "Forecast",
    "LogSource",
    "MetricRollup",
    "RequestLog",
    "User",
    "UserRole",
    "as_utc",
    "utcnow",
]
