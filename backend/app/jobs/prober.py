"""Active prober: synthetically exercise every registered API on a schedule.

Passive collection (proxy + SDK) only sees an API while somebody is calling it.
That leaves two blind spots the prober closes:

* A quiet API produces no data at all, so the dashboard cannot distinguish
  "healthy and idle" from "down".
* An outage that starts during a quiet period is invisible until the next real
  caller trips over it.

Probes are recorded with ``source='probe'`` so they stay distinguishable from
organic traffic in the raw table, while still contributing to the same
Golden-Signal rollups.
"""

from __future__ import annotations

import logging
import time
from urllib.parse import urlsplit

import httpx
from sqlmodel import Session, select

from app.config import settings
from app.database import engine
from app.models import ApiRegistry, LogSource
from app.routers.ingest import normalise_endpoint, record_call

logger = logging.getLogger(__name__)

#: Status recorded when the upstream did not answer at all.
UNREACHABLE_STATUS = 503


def probe_api(client: httpx.Client, session: Session, api: ApiRegistry) -> int:
    """Issue one probe against a registered API and record the result.

    Args:
        client: A reusable HTTP client, so a fleet-wide sweep opens one
            connection pool instead of one per API.
        session: Active database session.
        api: The registry row to probe.

    Returns:
        int: The status code recorded (``503`` when the upstream was
        unreachable).
    """
    endpoint = normalise_endpoint(urlsplit(api.upstream_url).path)
    started = time.perf_counter()
    try:
        response = client.get(api.upstream_url, timeout=settings.PROBE_TIMEOUT_SECONDS)
        status_code = response.status_code
        response_bytes = len(response.content) or None
    except httpx.HTTPError as exc:
        status_code = UNREACHABLE_STATUS
        response_bytes = None
        logger.warning("probe of %s (%s) failed: %s", api.name, api.upstream_url, exc)

    latency_ms = (time.perf_counter() - started) * 1000.0
    record_call(
        session,
        api_id=api.id or 0,
        endpoint=endpoint,
        method="GET",
        status_code=status_code,
        latency_ms=latency_ms,
        source=LogSource.PROBE,
        response_bytes=response_bytes,
    )
    return status_code


def probe_all(session: Session) -> int:
    """Probe every registered API once.

    Args:
        session: Active database session.

    Returns:
        int: Number of APIs probed.
    """
    apis = list(session.exec(select(ApiRegistry)).all())
    if not apis:
        return 0
    with httpx.Client(follow_redirects=True) as client:
        for api in apis:
            probe_api(client, session, api)
    return len(apis)


def prober_job() -> None:
    """Scheduler entry point: probe the whole fleet on its own session.

    Exceptions are logged rather than raised so one bad tick cannot take the
    scheduler thread down with it.
    """
    try:
        with Session(engine) as session:
            probed = probe_all(session)
        if probed:
            logger.debug("prober swept %d api(s)", probed)
    except Exception:
        logger.exception("prober job failed")
