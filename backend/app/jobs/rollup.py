"""Aggregate raw ``request_log`` rows into per-minute ``metric_rollup`` buckets.

This job is the hinge between PulseGrid's write path and its read path. Every
analytics endpoint and the dashboard read *only* from ``metric_rollup``, so no
dashboard query ever scans the raw append-only table.

Idempotency
-----------
Each run re-aggregates a trailing window (``ROLLUP_LOOKBACK_MINUTES``) rather
than only the minute that just closed. Rows can arrive late — a proxied call
that started before the minute boundary lands after it, and SDK batches are
flushed on the client's schedule — so a strictly forward-only job would
permanently under-count those buckets. Re-processing is safe because the
``(bucket, api_id, endpoint)`` unique constraint turns a repeat run into an
update rather than a duplicate.

Why percentiles are computed in Python
--------------------------------------
``percentile_cont`` is a PostgreSQL ordered-set aggregate with no SQLite
equivalent, and the test suite runs on SQLite. The window this job reads is
bounded to a few minutes of rows, so pulling them into the process and reducing
there costs little and keeps one code path across both engines. The volume-
sensitive part — the dashboard read path — remains pure SQL against the rollup
table.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlmodel import Session, select

from app.config import settings
from app.database import engine
from app.models import MetricRollup, RequestLog, utcnow

logger = logging.getLogger(__name__)


def as_utc(value: datetime) -> datetime:
    """Return ``value`` as a timezone-aware UTC datetime.

    SQLite has no timestamptz, so values round-trip as naive. Treating a naive
    value as UTC matches how it was written (:func:`app.models.utcnow`).

    Args:
        value: A timestamp read back from the database.

    Returns:
        datetime: The same instant, tagged UTC.
    """
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def minute_bucket(value: datetime) -> datetime:
    """Truncate a timestamp to its minute bucket.

    The Python equivalent of ``date_trunc('minute', time)``.

    Args:
        value: The timestamp to truncate.

    Returns:
        datetime: The start of the containing minute, in UTC.
    """
    return as_utc(value).replace(second=0, microsecond=0)


def percentile(sorted_values: list[float], fraction: float) -> float:
    """Linear-interpolation percentile over an already-sorted list.

    Matches ``numpy.percentile``'s default (and PostgreSQL's
    ``percentile_cont``) so the numbers agree with anything computed
    out-of-band in a notebook.

    Args:
        sorted_values: Ascending values; must not be empty.
        fraction: Percentile as a ratio, e.g. ``0.95``.

    Returns:
        float: The interpolated percentile.
    """
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = fraction * (len(sorted_values) - 1)
    low = int(position)
    high = min(low + 1, len(sorted_values) - 1)
    weight = position - low
    return sorted_values[low] * (1.0 - weight) + sorted_values[high] * weight


def compute_rollups(session: Session, window_min: int | None = None) -> int:
    """Aggregate the trailing window of raw rows into minute buckets.

    Args:
        session: Active database session.
        window_min: Look-back window in minutes. Defaults to
            ``settings.ROLLUP_LOOKBACK_MINUTES``.

    Returns:
        int: Number of ``metric_rollup`` rows written or refreshed.
    """
    lookback = window_min or settings.ROLLUP_LOOKBACK_MINUTES
    since = minute_bucket(utcnow() - timedelta(minutes=lookback))

    rows = session.exec(select(RequestLog).where(RequestLog.time >= since)).all()
    if not rows:
        return 0

    grouped: dict[tuple[datetime, int, str], list[RequestLog]] = defaultdict(list)
    for row in rows:
        grouped[(minute_bucket(row.time), row.api_id, row.endpoint)].append(row)

    # One query for every existing bucket in the window, rather than one lookup
    # per group: the window is small but the group count is not bounded.
    existing = {
        (as_utc(r.bucket), r.api_id, r.endpoint): r
        for r in session.exec(select(MetricRollup).where(MetricRollup.bucket >= since)).all()
    }

    written = 0
    for (bucket, api_id, endpoint), calls in grouped.items():
        latencies = sorted(call.latency_ms for call in calls)
        errors = sum(1 for call in calls if call.is_error)
        target = existing.get((bucket, api_id, endpoint)) or MetricRollup(
            bucket=bucket, api_id=api_id, endpoint=endpoint
        )
        target.req_count = len(calls)
        target.err_count = errors
        target.p50_ms = round(percentile(latencies, 0.50), 3)
        target.p95_ms = round(percentile(latencies, 0.95), 3)
        target.p99_ms = round(percentile(latencies, 0.99), 3)
        target.avg_ms = round(sum(latencies) / len(latencies), 3)
        session.add(target)
        written += 1

    session.commit()
    logger.debug("rollup wrote %d bucket(s) from %d raw row(s)", written, len(rows))
    return written


def rollup_job() -> None:
    """Scheduler entry point: run :func:`compute_rollups` on its own session.

    APScheduler runs jobs on a worker thread with no request context, so the
    job opens and closes its own session rather than borrowing a request's.
    Exceptions are logged rather than raised: a failed tick must not kill the
    scheduler thread and take every later tick with it.
    """
    try:
        with Session(engine) as session:
            written = compute_rollups(session)
        if written:
            logger.info("rollup job aggregated %d bucket(s)", written)
    except Exception:  # noqa: BLE001 - a job must never take the scheduler down
        logger.exception("rollup job failed")
