"""Initial PulseGrid schema: registry, raw request log, rollups, alerts, forecasts.

Revision ID: 0001_initial
Revises:
Create Date: 2025-01-01 00:00:00+00:00

Design notes (these are the reasoning behind the DB-design decisions)
---------------------------------------------------------------------

**Raw log vs rollup separation.** ``request_log`` is the write-heavy,
append-only fact table — one row per observed API call, inserted by the reverse
proxy, the ingest endpoint and the active prober. ``metric_rollup`` is the
read-heavy aggregate — one row per ``(minute bucket, api, endpoint)``, produced
by an APScheduler job with ``date_trunc('minute', time)`` GROUP BY queries.
Every analytics endpoint and every dashboard chart reads only from
``metric_rollup``, so a dashboard refresh never scans raw rows. That is what
gives a plain PostgreSQL instance the query profile of a time-series database.

**BRIN on ``request_log.time``.** A B-tree stores one entry per row; on an
ingest-scale log that index quickly outgrows the useful working set. BRIN
instead stores a min/max summary per range of physical blocks. Because
``request_log`` is append-only and therefore already physically ordered by
``time``, those summaries are extremely tight — a time-range scan can skip
almost every block that cannot match, at an index size measured in kilobytes
rather than hundreds of megabytes. BRIN is created with raw SQL because
SQLAlchemy's ``op.create_index`` has no portable BRIN spelling.

**Composite B-trees.** BRIN is block-level, so it cannot answer "the last 15
minutes *for API 3*" selectively. ``(api_id, time DESC)`` on ``request_log``
and ``(api_id, bucket DESC)`` on ``metric_rollup`` cover exactly that pattern;
``DESC`` matches the ``ORDER BY ... DESC LIMIT n`` the dashboard issues.

**Unique ``(bucket, api_id, endpoint)``.** Makes the rollup job idempotent. It
re-processes a short trailing window to catch late-arriving rows, so it must be
able to ``ON CONFLICT ... DO UPDATE`` rather than duplicate buckets.

**Enums as VARCHAR.** ``role``, ``source``, ``type`` and ``severity`` are plain
``VARCHAR`` rather than native PostgreSQL ``ENUM`` types. Adding a value to a
native enum requires a migration and locks; a VARCHAR column validated by the
Pydantic layer costs nothing and keeps the schema portable to SQLite for tests.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create every PulseGrid table and index."""
    # ----------------------------------------------------------------- users
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=16), server_default="viewer", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="Operator accounts that own registered APIs and read the dashboard.",
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # ---------------------------------------------------------- api_registry
    op.create_table(
        "api_registry",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("base_url", sa.String(length=512), nullable=False),
        sa.Column("upstream_url", sa.String(length=512), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("auth_type", sa.String(length=32), nullable=True),
        sa.Column("slo_target", sa.Float(), server_default=sa.text("0.99"), nullable=False),
        sa.Column("slo_latency_ms", sa.Integer(), server_default=sa.text("500"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        comment="Catalogue of monitored APIs, their upstreams and their SLO targets.",
    )
    op.create_index("ix_api_registry_name", "api_registry", ["name"], unique=False)
    op.create_index(
        "ix_api_registry_owner_user_id", "api_registry", ["owner_user_id"], unique=False
    )

    # ----------------------------------------------------------- request_log
    op.create_table(
        "request_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("api_id", sa.Integer(), nullable=False),
        sa.Column("endpoint", sa.String(length=512), nullable=False),
        sa.Column("method", sa.String(length=10), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("request_bytes", sa.Integer(), nullable=True),
        sa.Column("response_bytes", sa.Integer(), nullable=True),
        sa.Column("client_ip", sa.String(length=45), nullable=True),
        sa.Column("is_error", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("source", sa.String(length=16), server_default="proxy", nullable=False),
        sa.ForeignKeyConstraint(["api_id"], ["api_registry.id"]),
        sa.PrimaryKeyConstraint("id"),
        comment=(
            "Raw append-only request facts (write-heavy). BRIN on time + "
            "B-tree on (api_id, time DESC); aggregated into metric_rollup."
        ),
    )
    # Per-API recent-window queries: "last N minutes for API 3".
    op.create_index(
        "ix_request_log_api_id_time",
        "request_log",
        ["api_id", sa.text("time DESC")],
        unique=False,
    )
    # BRIN: block-range summaries over append-only, time-ordered data. Tiny on
    # disk, and range scans skip every block whose summary cannot match.
    op.execute("CREATE INDEX ix_request_log_time_brin ON request_log USING BRIN (time);")

    # --------------------------------------------------------- metric_rollup
    op.create_table(
        "metric_rollup",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bucket", sa.DateTime(timezone=True), nullable=False),
        sa.Column("api_id", sa.Integer(), nullable=False),
        sa.Column("endpoint", sa.String(length=512), nullable=False),
        sa.Column("req_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("err_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("p50_ms", sa.Float(), server_default=sa.text("0"), nullable=False),
        sa.Column("p95_ms", sa.Float(), server_default=sa.text("0"), nullable=False),
        sa.Column("p99_ms", sa.Float(), server_default=sa.text("0"), nullable=False),
        sa.Column("avg_ms", sa.Float(), server_default=sa.text("0"), nullable=False),
        sa.Column("saturation_pct", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["api_id"], ["api_registry.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "bucket", "api_id", "endpoint", name="uq_metric_rollup_bucket_api_endpoint"
        ),
        comment=(
            "Per-minute Golden-Signal aggregates (read-heavy). Serves all "
            "analytics endpoints so dashboards never scan request_log."
        ),
    )
    op.create_index(
        "ix_metric_rollup_api_id_bucket",
        "metric_rollup",
        ["api_id", sa.text("bucket DESC")],
        unique=False,
    )

    # ----------------------------------------------------------------- alert
    op.create_table(
        "alert",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("api_id", sa.Integer(), nullable=False),
        sa.Column("endpoint", sa.String(length=512), nullable=True),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("severity", sa.String(length=16), server_default="warning", nullable=False),
        sa.Column("signal", sa.String(length=32), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("metric_value", sa.Float(), nullable=False),
        sa.Column("expected_range", sa.String(length=64), nullable=False),
        sa.Column(
            "fired_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["api_id"], ["api_registry.id"]),
        sa.PrimaryKeyConstraint("id"),
        comment="Fired anomaly / SLO-burn / health alerts with their explanations.",
    )
    op.create_index(
        "ix_alert_api_id_fired_at",
        "alert",
        ["api_id", sa.text("fired_at DESC")],
        unique=False,
    )

    # -------------------------------------------------------------- forecast
    op.create_table(
        "forecast",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("api_id", sa.Integer(), nullable=False),
        sa.Column("endpoint", sa.String(length=512), nullable=True),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("horizon_min", sa.Integer(), nullable=False),
        sa.Column("yhat", sa.Float(), nullable=False),
        sa.Column("yhat_lower", sa.Float(), nullable=False),
        sa.Column("yhat_upper", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["api_id"], ["api_registry.id"]),
        sa.PrimaryKeyConstraint("id"),
        comment="Traffic forecast points with prediction intervals, written by the ML job.",
    )
    op.create_index(
        "ix_forecast_api_id_generated_at",
        "forecast",
        ["api_id", sa.text("generated_at DESC")],
        unique=False,
    )


def downgrade() -> None:
    """Drop every PulseGrid table and index, in reverse dependency order."""
    op.drop_index("ix_forecast_api_id_generated_at", table_name="forecast")
    op.drop_table("forecast")

    op.drop_index("ix_alert_api_id_fired_at", table_name="alert")
    op.drop_table("alert")

    op.drop_index("ix_metric_rollup_api_id_bucket", table_name="metric_rollup")
    op.drop_table("metric_rollup")

    op.execute("DROP INDEX IF EXISTS ix_request_log_time_brin;")
    op.drop_index("ix_request_log_api_id_time", table_name="request_log")
    op.drop_table("request_log")

    op.drop_index("ix_api_registry_owner_user_id", table_name="api_registry")
    op.drop_index("ix_api_registry_name", table_name="api_registry")
    op.drop_table("api_registry")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
