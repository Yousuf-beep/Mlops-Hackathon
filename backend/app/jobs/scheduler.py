"""APScheduler wiring for PulseGrid's periodic work.

Why APScheduler and not Celery: PulseGrid's background work is a handful of
short, idempotent, single-tenant jobs (rollup, probe, retrain). APScheduler
runs them inside the API process with zero extra infrastructure — no broker, no
worker image, no second deployment — which keeps the whole system deployable
with one ``docker compose up``. Celery's fan-out and durability guarantees
would buy nothing here and cost a Redis/RabbitMQ dependency.

Registered jobs:
    * ``heartbeat_job`` — liveness line proving the scheduler thread is alive
    * ``prober_job``    — actively probe every registered API
    * ``rollup_job``    — aggregate ``request_log`` into ``metric_rollup``
    * ``anomaly_job``   — score recent buckets, write ``alert`` rows
    * ``forecast_job``  — refit the traffic forecast

Every period is configurable. The defaults run the prober faster than the
rollup on purpose, so each closed bucket covers several observations and its
percentiles mean something.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings
from app.jobs.ml_jobs import anomaly_job, forecast_job
from app.jobs.prober import prober_job
from app.jobs.rollup import rollup_job

logger = logging.getLogger(__name__)

#: Process-wide scheduler. ``coalesce`` collapses missed runs into one and
#: ``max_instances=1`` prevents a slow run from overlapping the next tick —
#: both matter for rollup jobs that must stay idempotent.
scheduler = BackgroundScheduler(
    timezone="UTC",
    job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 30},
)

HEARTBEAT_JOB_ID = "heartbeat"


def heartbeat_job() -> None:
    """Log a liveness line so scheduler failures are visible in the API logs.

    Kept alongside the real jobs because it is the only one that runs
    unconditionally: if the heartbeat stops appearing, the scheduler thread
    died, rather than the fleet simply having nothing to do.
    """
    logger.info(
        "scheduler heartbeat at %s (env=%s)",
        datetime.now(UTC).isoformat(),
        settings.ENV,
    )


def register_jobs(target: BackgroundScheduler | None = None) -> BackgroundScheduler:
    """Register every periodic job on the scheduler.

    Idempotent: ``replace_existing=True`` means a re-import or a reload cycle
    cannot end up with duplicate jobs.

    Args:
        target: Scheduler to register on. Defaults to the module-level
            :data:`scheduler`; injectable for tests.

    Returns:
        BackgroundScheduler: The scheduler the jobs were registered on.
    """
    sched = target or scheduler
    specs = (
        (
            heartbeat_job,
            HEARTBEAT_JOB_ID,
            "no-op liveness heartbeat",
            settings.HEARTBEAT_INTERVAL_SECONDS,
        ),
        (prober_job, "prober", "actively probe registered APIs", settings.PROBE_INTERVAL_SECONDS),
        (
            rollup_job,
            "rollup",
            "aggregate request_log into metric_rollup",
            settings.ROLLUP_INTERVAL_SECONDS,
        ),
        (
            anomaly_job,
            "anomaly",
            "score recent buckets and raise alerts",
            settings.ANOMALY_INTERVAL_SECONDS,
        ),
        (
            forecast_job,
            "forecast",
            "refit the traffic forecast",
            settings.FORECAST_INTERVAL_SECONDS,
        ),
    )
    for func, job_id, name, seconds in specs:
        sched.add_job(
            func,
            trigger=IntervalTrigger(seconds=seconds),
            id=job_id,
            name=name,
            replace_existing=True,
        )
    logger.info("registered %d scheduled job(s)", len(sched.get_jobs()))
    return sched


def start_scheduler() -> BackgroundScheduler | None:
    """Register jobs and start the scheduler, honouring ``SCHEDULER_ENABLED``.

    Returns:
        BackgroundScheduler | None: The running scheduler, or ``None`` when
        scheduling is disabled (tests, one-off management commands).
    """
    if not settings.SCHEDULER_ENABLED:
        logger.info("scheduler disabled via SCHEDULER_ENABLED=false")
        return None
    register_jobs()
    if not scheduler.running:
        scheduler.start()
        logger.info("APScheduler started")
    return scheduler


def shutdown_scheduler() -> None:
    """Stop the scheduler, waiting for any in-flight job to finish."""
    if scheduler.running:
        scheduler.shutdown(wait=True)
        logger.info("APScheduler stopped")
