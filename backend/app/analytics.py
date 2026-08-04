"""Golden-Signal queries over ``metric_rollup``.

Every read here targets the pre-aggregated table, never ``request_log``. That
is the whole point of the split described in :mod:`app.models`: a dashboard
refresh touches one row per minute per endpoint instead of one row per request.

Combining per-endpoint percentiles
----------------------------------
When a caller asks for an API-wide latency series, the rollup holds one
percentile per *endpoint* per minute. Percentiles are not additive, and the
rollup deliberately discards the raw distribution that would let us recombine
them exactly. PulseGrid therefore reports the **request-weighted mean** of the
endpoint percentiles: an endpoint serving 90% of the traffic dominates the
API-level number, which is the behaviour an operator expects. Ask for a single
``endpoint`` to get an exact figure.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlmodel import Session, col, select

from app.models import Alert, ApiRegistry, MetricRollup, as_utc, utcnow
from app.schemas import (
    AnomalyRead,
    ApiOverviewItem,
    EndpointBreakdownItem,
    EndpointBreakdownResponse,
    HealthScoreResponse,
    HealthTimelinePoint,
    HealthTimelineResponse,
    HeatmapCell,
    HeatmapResponse,
    SummaryResponse,
    TimeseriesPoint,
)

#: Rollup columns a latency series may project.
LATENCY_COLUMNS = {
    "p50": MetricRollup.p50_ms,
    "p95": MetricRollup.p95_ms,
    "p99": MetricRollup.p99_ms,
    "avg": MetricRollup.avg_ms,
}

#: Share of the score that latency can move. Availability is *not* weighted
#: alongside it — it gates the whole score (see :func:`health_score`), because a
#: fast error is still an outage and a weighted sum would let a snappy, totally
#: broken API keep a third of its marks.
_LATENCY_WEIGHT = 0.35
_LATENCY_FLOOR = 1.0 - _LATENCY_WEIGHT

#: Score thresholds for the traffic-light status shown on the dashboard.
_HEALTHY_SCORE = 90.0
_DEGRADED_SCORE = 70.0


def window_start(window_min: int) -> datetime:
    """Return the inclusive lower bound of a look-back window.

    Args:
        window_min: Window length in minutes.

    Returns:
        datetime: ``now - window_min``, truncated to the minute so the bound
        lands on a bucket boundary.
    """
    return (utcnow() - timedelta(minutes=window_min)).replace(second=0, microsecond=0)


def _scoped(statement, api_id: int, since: datetime, endpoint: str | None):  # type: ignore[no-untyped-def]
    """Apply the standard API / window / endpoint filters to a statement.

    Args:
        statement: The select being built.
        api_id: Registry id to restrict to.
        since: Inclusive lower bound on ``bucket``.
        endpoint: Optional endpoint template filter.

    Returns:
        The statement with the filters applied.
    """
    statement = statement.where(
        col(MetricRollup.api_id) == api_id, col(MetricRollup.bucket) >= since
    )
    if endpoint is not None:
        statement = statement.where(col(MetricRollup.endpoint) == endpoint)
    return statement


def _lower_bound(window_min: int, since: datetime | None) -> datetime:
    """Resolve a series' effective lower bound.

    Args:
        window_min: Look-back window in minutes, used when ``since`` is unset.
        since: Caller-supplied cursor for an incremental fetch — the dashboard
            already holds every point up to and including this bucket, so it
            asks for only what landed after it instead of refetching the whole
            window on every SSE tick.

    Returns:
        datetime: The later of the two bounds, so a stale ``since`` from a
        client that has been offline can never re-open a wider window than
        ``window_min`` already implies. Callers are expected to have already
        normalised ``since`` with :func:`app.models.as_utc`.
    """
    floor = window_start(window_min)
    return max(floor, since) if since is not None else floor


def latency_series(
    session: Session,
    api_id: int,
    window_min: int,
    endpoint: str | None = None,
    percentile: str = "p95",
    since: datetime | None = None,
) -> list[TimeseriesPoint]:
    """Return a latency percentile series, one point per minute bucket.

    Args:
        session: Active database session.
        api_id: Registry id of the API.
        window_min: Look-back window in minutes.
        endpoint: Optional endpoint filter.
        percentile: One of ``p50``, ``p95``, ``p99``, ``avg``.
        since: Return only buckets strictly after this cursor, for an
            incremental (append-only) fetch. ``None`` returns the full window.

    Returns:
        list[TimeseriesPoint]: Points in ascending bucket order.
    """
    since = as_utc(since) if since is not None else None
    column = LATENCY_COLUMNS[percentile]
    weighted = func.sum(column * MetricRollup.req_count) / func.nullif(
        func.sum(MetricRollup.req_count), 0
    )
    statement = _scoped(
        select(MetricRollup.bucket, weighted), api_id, _lower_bound(window_min, since), endpoint
    )
    if since is not None:
        statement = statement.where(col(MetricRollup.bucket) > since)
    statement = statement.group_by(col(MetricRollup.bucket)).order_by(col(MetricRollup.bucket))
    return [
        TimeseriesPoint(bucket=bucket, value=round(float(value or 0.0), 3))
        for bucket, value in session.exec(statement).all()
    ]


def traffic_series(
    session: Session,
    api_id: int,
    window_min: int,
    endpoint: str | None = None,
    since: datetime | None = None,
) -> list[TimeseriesPoint]:
    """Return the requests-per-minute series.

    Args:
        session: Active database session.
        api_id: Registry id of the API.
        window_min: Look-back window in minutes.
        endpoint: Optional endpoint filter.
        since: Return only buckets strictly after this cursor. ``None``
            returns the full window.

    Returns:
        list[TimeseriesPoint]: Request counts in ascending bucket order.
    """
    since = as_utc(since) if since is not None else None
    statement = _scoped(
        select(MetricRollup.bucket, func.sum(MetricRollup.req_count)),
        api_id,
        _lower_bound(window_min, since),
        endpoint,
    )
    if since is not None:
        statement = statement.where(col(MetricRollup.bucket) > since)
    statement = statement.group_by(col(MetricRollup.bucket)).order_by(col(MetricRollup.bucket))
    return [
        TimeseriesPoint(bucket=bucket, value=float(total or 0))
        for bucket, total in session.exec(statement).all()
    ]


def error_series(
    session: Session,
    api_id: int,
    window_min: int,
    endpoint: str | None = None,
    since: datetime | None = None,
) -> list[TimeseriesPoint]:
    """Return the error-rate series as a percentage of requests.

    Args:
        session: Active database session.
        api_id: Registry id of the API.
        window_min: Look-back window in minutes.
        endpoint: Optional endpoint filter.
        since: Return only buckets strictly after this cursor. ``None``
            returns the full window.

    Returns:
        list[TimeseriesPoint]: Error rates in percent, ascending by bucket.
    """
    since = as_utc(since) if since is not None else None
    rate = (
        100.0 * func.sum(MetricRollup.err_count) / func.nullif(func.sum(MetricRollup.req_count), 0)
    )
    statement = _scoped(
        select(MetricRollup.bucket, rate), api_id, _lower_bound(window_min, since), endpoint
    )
    if since is not None:
        statement = statement.where(col(MetricRollup.bucket) > since)
    statement = statement.group_by(col(MetricRollup.bucket)).order_by(col(MetricRollup.bucket))
    return [
        TimeseriesPoint(bucket=bucket, value=round(float(value or 0.0), 3))
        for bucket, value in session.exec(statement).all()
    ]


def _aggregate(session: Session, api_id: int, since: datetime) -> tuple[int, int, float]:
    """Reduce a window of rollups to totals for one API.

    Args:
        session: Active database session.
        api_id: Registry id of the API.
        since: Inclusive lower bound on ``bucket``.

    Returns:
        tuple[int, int, float]: ``(req_count, err_count, weighted p95)``.
    """
    statement = select(
        func.sum(MetricRollup.req_count),
        func.sum(MetricRollup.err_count),
        func.sum(MetricRollup.p95_ms * MetricRollup.req_count),
    ).where(col(MetricRollup.api_id) == api_id, col(MetricRollup.bucket) >= since)
    requests, errors, weighted_latency = session.exec(statement).one()
    requests = int(requests or 0)
    errors = int(errors or 0)
    p95 = float(weighted_latency or 0.0) / requests if requests else 0.0
    return requests, errors, p95


def health_score(
    requests: int, errors: int, p95_ms: float, slo_target: float, slo_latency_ms: int
) -> float:
    """Blend availability and latency into a single 0-100 score.

    Both components are measured *against the API's own SLO*, so a 300 ms API
    with a 500 ms objective scores as well as a 30 ms API with a 50 ms one.
    Meeting an objective saturates its component at 1.0 — beating it earns no
    credit that could mask a failure in the other signal.

    Availability multiplies the score rather than contributing a share of it:
    an API returning nothing but errors scores 0 however fast it does so.
    Latency then trims up to :data:`_LATENCY_WEIGHT` of what remains.

    Args:
        requests: Total requests in the window.
        errors: Total errored requests in the window.
        p95_ms: Weighted p95 latency in the window.
        slo_target: Availability objective as a ratio.
        slo_latency_ms: Latency objective in milliseconds.

    Returns:
        float: The score, ``100.0`` when there is no traffic to judge.
    """
    if requests == 0:
        return 100.0
    availability = 1.0 - (errors / requests)
    availability_component = min(1.0, availability / slo_target) if slo_target else 1.0
    latency_component = min(1.0, slo_latency_ms / p95_ms) if p95_ms > 0 else 1.0
    score = 100.0 * availability_component * (_LATENCY_FLOOR + _LATENCY_WEIGHT * latency_component)
    return round(max(0.0, min(100.0, score)), 2)


def _status_for(score: float, requests: int) -> str:
    """Map a score to the dashboard's traffic-light status.

    Args:
        score: Composite health score.
        requests: Requests seen in the window; zero means nothing to judge.

    Returns:
        str: ``healthy``, ``degraded``, ``critical`` or ``no_data``.
    """
    if requests == 0:
        return "no_data"
    if score >= _HEALTHY_SCORE:
        return "healthy"
    if score >= _DEGRADED_SCORE:
        return "degraded"
    return "critical"


def api_health(session: Session, api: ApiRegistry, window_min: int) -> HealthScoreResponse:
    """Compute the composite health score for one API.

    Args:
        session: Active database session.
        api: The registry row being scored.
        window_min: Look-back window in minutes.

    Returns:
        HealthScoreResponse: The score and the inputs that produced it.
    """
    requests, errors, p95 = _aggregate(session, api.id or 0, window_start(window_min))
    availability = 1.0 - (errors / requests) if requests else 1.0
    return HealthScoreResponse(
        api_id=api.id or 0,
        score=health_score(requests, errors, p95, api.slo_target, api.slo_latency_ms),
        slo_target=api.slo_target,
        availability=round(availability, 5),
        p95_ms=round(p95, 3),
    )


def open_alert_counts(session: Session) -> dict[int, int]:
    """Count still-firing alerts per API.

    Args:
        session: Active database session.

    Returns:
        dict[int, int]: ``api_id`` → number of unresolved alerts.
    """
    statement = (
        select(Alert.api_id, func.count())
        .where(col(Alert.resolved_at).is_(None))
        .group_by(col(Alert.api_id))
    )
    return {api_id: int(count) for api_id, count in session.exec(statement).all()}


def anomaly_reads(session: Session, alerts: list[Alert]) -> list[AnomalyRead]:
    """Attach each alert's API name for the wire format, without N+1 lookups.

    ``Alert`` only stores ``api_id``; the dashboard wants the name on every
    row (the alert feed, the SSE snapshot). One batch query for the distinct
    ids involved keeps this to two queries total regardless of alert count.

    Args:
        session: Active database session.
        alerts: Rows to project, in whatever order the caller already sorted
            them.

    Returns:
        list[AnomalyRead]: Same order as ``alerts``, each carrying its API's
        name.
    """
    if not alerts:
        return []
    api_ids = {alert.api_id for alert in alerts}
    names = {
        api_id: name
        for api_id, name in session.exec(
            select(ApiRegistry.id, ApiRegistry.name).where(col(ApiRegistry.id).in_(api_ids))
        ).all()
    }
    return [
        AnomalyRead(
            id=alert.id or 0,
            api_id=alert.api_id,
            api_name=names.get(alert.api_id, f"API {alert.api_id}"),
            endpoint=alert.endpoint,
            type=alert.type,
            severity=alert.severity,
            signal=alert.signal,
            explanation=alert.explanation,
            metric_value=alert.metric_value,
            expected_range=alert.expected_range,
            confidence=alert.confidence,
            fired_at=alert.fired_at,
            resolved_at=alert.resolved_at,
        )
        for alert in alerts
    ]


def api_overview(session: Session, window_min: int) -> list[ApiOverviewItem]:
    """Build the per-API standing rows for the fleet overview.

    Args:
        session: Active database session.
        window_min: Look-back window in minutes.

    Returns:
        list[ApiOverviewItem]: One row per registered API, worst score first.
    """
    since = window_start(window_min)
    alerts = open_alert_counts(session)
    items: list[ApiOverviewItem] = []
    for api in session.exec(select(ApiRegistry).order_by(col(ApiRegistry.id))).all():
        requests, errors, p95 = _aggregate(session, api.id or 0, since)
        availability = 1.0 - (errors / requests) if requests else 1.0
        score = health_score(requests, errors, p95, api.slo_target, api.slo_latency_ms)
        items.append(
            ApiOverviewItem(
                api_id=api.id or 0,
                name=api.name,
                score=score,
                availability=round(availability, 5),
                error_rate=round(100.0 * (errors / requests) if requests else 0.0, 3),
                p95_ms=round(p95, 3),
                req_count=requests,
                slo_target=api.slo_target,
                slo_latency_ms=api.slo_latency_ms,
                open_alerts=alerts.get(api.id or 0, 0),
                status=_status_for(score, requests),  # type: ignore[arg-type]
            )
        )
    items.sort(key=lambda item: (item.score, -item.req_count))
    return items


def fleet_summary(session: Session, window_min: int) -> SummaryResponse:
    """Compute the fleet-wide header tiles.

    Args:
        session: Active database session.
        window_min: Look-back window in minutes.

    Returns:
        SummaryResponse: Totals across every registered API.
    """
    since = window_start(window_min)
    api_count = int(session.exec(select(func.count()).select_from(ApiRegistry)).one() or 0)
    requests, errors, weighted = session.exec(
        select(
            func.sum(MetricRollup.req_count),
            func.sum(MetricRollup.err_count),
            func.sum(MetricRollup.p95_ms * MetricRollup.req_count),
        ).where(col(MetricRollup.bucket) >= since)
    ).one()
    requests = int(requests or 0)
    errors = int(errors or 0)
    open_alerts = int(
        session.exec(
            select(func.count()).select_from(Alert).where(col(Alert.resolved_at).is_(None))
        ).one()
        or 0
    )
    return SummaryResponse(
        api_count=api_count,
        total_requests=requests,
        error_rate=round(100.0 * (errors / requests) if requests else 0.0, 3),
        p95_ms=round(float(weighted or 0.0) / requests if requests else 0.0, 3),
        open_alerts=open_alerts,
    )


def endpoint_breakdown(
    session: Session, api_id: int, window_min: int, limit: int = 50
) -> EndpointBreakdownResponse:
    """Aggregate one API's rollups per endpoint over a window.

    Args:
        session: Active database session.
        api_id: Registry id of the API.
        window_min: Look-back window in minutes.
        limit: Maximum number of endpoints to return.

    Returns:
        EndpointBreakdownResponse: Endpoints ordered by p95 latency, slowest
        first — the order an operator triages in.
    """
    since = window_start(window_min)
    requests = func.sum(MetricRollup.req_count)
    safe_requests = func.nullif(requests, 0)
    statement = (
        select(
            MetricRollup.endpoint,
            requests,
            func.sum(MetricRollup.err_count),
            func.sum(MetricRollup.p50_ms * MetricRollup.req_count) / safe_requests,
            func.sum(MetricRollup.p95_ms * MetricRollup.req_count) / safe_requests,
            func.sum(MetricRollup.p99_ms * MetricRollup.req_count) / safe_requests,
            func.sum(MetricRollup.avg_ms * MetricRollup.req_count) / safe_requests,
        )
        .where(col(MetricRollup.api_id) == api_id, col(MetricRollup.bucket) >= since)
        .group_by(col(MetricRollup.endpoint))
        .limit(limit)
    )
    items = [
        EndpointBreakdownItem(
            endpoint=endpoint,
            req_count=int(req or 0),
            err_count=int(err or 0),
            error_rate=round(100.0 * (int(err or 0) / int(req)) if req else 0.0, 3),
            p50_ms=round(float(p50 or 0.0), 3),
            p95_ms=round(float(p95 or 0.0), 3),
            p99_ms=round(float(p99 or 0.0), 3),
            avg_ms=round(float(avg or 0.0), 3),
        )
        for endpoint, req, err, p50, p95, p99, avg in session.exec(statement).all()
    ]
    items.sort(key=lambda item: item.p95_ms, reverse=True)
    return EndpointBreakdownResponse(api_id=api_id, window_min=window_min, endpoints=items)


def health_timeline(session: Session, api: ApiRegistry, window_min: int) -> HealthTimelineResponse:
    """Return one API's composite health score, one point per minute bucket.

    Reuses :func:`health_score` — the exact function behind the current-moment
    score on every API row and tile — applied per bucket instead of once over
    the whole window, so the dashboard can show an up/down history rather than
    only "healthy right now".

    Args:
        session: Active database session.
        api: The registry row being scored.
        window_min: Look-back window in minutes.

    Returns:
        HealthTimelineResponse: Ascending by bucket.
    """
    since = window_start(window_min)
    statement = (
        select(
            MetricRollup.bucket,
            func.sum(MetricRollup.req_count),
            func.sum(MetricRollup.err_count),
            func.sum(MetricRollup.p95_ms * MetricRollup.req_count),
        )
        .where(col(MetricRollup.api_id) == api.id, col(MetricRollup.bucket) >= since)
        .group_by(col(MetricRollup.bucket))
        .order_by(col(MetricRollup.bucket))
    )
    points = []
    for bucket, requests, errors, weighted in session.exec(statement).all():
        requests = int(requests or 0)
        errors = int(errors or 0)
        p95 = float(weighted or 0.0) / requests if requests else 0.0
        score = health_score(requests, errors, p95, api.slo_target, api.slo_latency_ms)
        points.append(HealthTimelinePoint(bucket=bucket, score=score, req_count=requests))
    return HealthTimelineResponse(api_id=api.id or 0, window_min=window_min, points=points)


#: Endpoints shown on the heatmap. More than this and the cell grid stops
#: being legible, so the busiest ones by volume win.
_HEATMAP_MAX_ENDPOINTS = 12


def request_heatmap(
    session: Session, api_id: int, window_min: int, max_endpoints: int = _HEATMAP_MAX_ENDPOINTS
) -> HeatmapResponse:
    """Return a (time bucket, endpoint) request-volume matrix for one API.

    Deliberately per-minute rather than pre-binned into coarser cells: it is
    the same grain ``metric_rollup`` already stores, so no extra aggregation
    is needed here, and the dashboard picks its own display resolution (e.g.
    binning 5 buckets per heatmap column on a 6h window) without a round trip
    for every zoom level.

    Args:
        session: Active database session.
        api_id: Registry id of the API.
        window_min: Look-back window in minutes.
        max_endpoints: Cap on distinct endpoints included, busiest first.

    Returns:
        HeatmapResponse: One cell per ``(bucket, endpoint)`` with traffic in
        the window, restricted to the busiest ``max_endpoints`` endpoints.
    """
    since = window_start(window_min)
    statement = (
        select(MetricRollup.bucket, MetricRollup.endpoint, MetricRollup.req_count)
        .where(col(MetricRollup.api_id) == api_id, col(MetricRollup.bucket) >= since)
        .order_by(col(MetricRollup.bucket))
    )
    rows = session.exec(statement).all()

    totals: dict[str, int] = defaultdict(int)
    for _, endpoint, req_count in rows:
        totals[endpoint] += int(req_count or 0)
    top_endpoints = {
        endpoint
        for endpoint, _ in sorted(totals.items(), key=lambda item: item[1], reverse=True)[
            :max_endpoints
        ]
    }

    cells = [
        HeatmapCell(bucket=bucket, endpoint=endpoint, req_count=int(req_count or 0))
        for bucket, endpoint, req_count in rows
        if endpoint in top_endpoints
    ]
    return HeatmapResponse(api_id=api_id, window_min=window_min, cells=cells)


__all__ = [
    "anomaly_reads",
    "api_health",
    "api_overview",
    "endpoint_breakdown",
    "error_series",
    "fleet_summary",
    "health_score",
    "health_timeline",
    "latency_series",
    "open_alert_counts",
    "request_heatmap",
    "traffic_series",
    "window_start",
]
