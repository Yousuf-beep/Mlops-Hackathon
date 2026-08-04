"""Golden-Signal analytics routes (latency, traffic, errors, health, summary).

Every handler here reads exclusively from ``metric_rollup`` — never from
``request_log`` — which is the whole point of the raw-log/rollup split described
in :mod:`app.models`. The query bodies live in :mod:`app.analytics` so the SSE
stream can serve the same numbers without going back out through HTTP.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from app import analytics as queries
from app.database import get_session
from app.models import ApiRegistry, utcnow
from app.schemas import (
    EndpointBreakdownResponse,
    ErrorResponse,
    HealthScoreResponse,
    HealthTimelineResponse,
    HeatmapResponse,
    OverviewResponse,
    SummaryResponse,
    TimeseriesResponse,
)

router = APIRouter(prefix="/v1/analytics", tags=["analytics"])

SessionDep = Annotated[Session, Depends(get_session)]

WindowParam = Annotated[int, Query(ge=1, le=1440, description="Look-back window in minutes.")]
ApiIdParam = Annotated[int, Query(description="Registry id of the API to query.")]
EndpointParam = Annotated[str | None, Query(description="Restrict to one endpoint template.")]
SinceParam = Annotated[
    datetime | None,
    Query(
        description=(
            "Return only buckets strictly after this timestamp, for an "
            "incremental fetch. Omit for the full window."
        )
    ),
]

_NOT_FOUND = {404: {"model": ErrorResponse, "description": "API not found"}}


def _require_api(api_id: int, session: Session) -> ApiRegistry:
    """Load a registry row or fail with 404.

    Args:
        api_id: Registry id supplied by the caller.
        session: Active database session.

    Returns:
        ApiRegistry: The requested row.

    Raises:
        HTTPException: 404 when the API is not registered.
    """
    api = session.get(ApiRegistry, api_id)
    if api is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="api not found")
    return api


@router.get(
    "/latency",
    response_model=TimeseriesResponse,
    summary="Latency percentiles over a window",
    responses=_NOT_FOUND,
)
def latency(
    api_id: ApiIdParam,
    session: SessionDep,
    window_min: WindowParam = 60,
    endpoint: EndpointParam = None,
    percentile: Annotated[str, Query(pattern="^(p50|p95|p99|avg)$")] = "p95",
    since: SinceParam = None,
) -> TimeseriesResponse:
    """Return a latency percentile series from ``metric_rollup``.

    Args:
        api_id: Registry id of the API.
        session: Active database session.
        window_min: Look-back window in minutes.
        endpoint: Optional endpoint filter.
        percentile: Which latency column to project.
        since: Return only points after this cursor, for incremental fetches.

    Returns:
        TimeseriesResponse: One point per minute bucket, ascending.
    """
    _require_api(api_id, session)
    return TimeseriesResponse(
        api_id=api_id,
        endpoint=endpoint,
        metric=f"latency.{percentile}",
        points=queries.latency_series(session, api_id, window_min, endpoint, percentile, since),
    )


@router.get(
    "/traffic",
    response_model=TimeseriesResponse,
    summary="Request-rate series over a window",
    responses=_NOT_FOUND,
)
def traffic(
    api_id: ApiIdParam,
    session: SessionDep,
    window_min: WindowParam = 60,
    endpoint: EndpointParam = None,
    since: SinceParam = None,
) -> TimeseriesResponse:
    """Return the requests-per-minute series from ``metric_rollup``.

    Args:
        api_id: Registry id of the API.
        session: Active database session.
        window_min: Look-back window in minutes.
        endpoint: Optional endpoint filter.
        since: Return only points after this cursor, for incremental fetches.

    Returns:
        TimeseriesResponse: Request counts per minute bucket.
    """
    _require_api(api_id, session)
    return TimeseriesResponse(
        api_id=api_id,
        endpoint=endpoint,
        metric="traffic.req_per_min",
        points=queries.traffic_series(session, api_id, window_min, endpoint, since),
    )


@router.get(
    "/errors",
    response_model=TimeseriesResponse,
    summary="Error-rate series over a window",
    responses=_NOT_FOUND,
)
def errors(
    api_id: ApiIdParam,
    session: SessionDep,
    window_min: WindowParam = 60,
    endpoint: EndpointParam = None,
    since: SinceParam = None,
) -> TimeseriesResponse:
    """Return the error-rate series from ``metric_rollup``.

    Args:
        api_id: Registry id of the API.
        session: Active database session.
        window_min: Look-back window in minutes.
        endpoint: Optional endpoint filter.
        since: Return only points after this cursor, for incremental fetches.

    Returns:
        TimeseriesResponse: Error rate in percent per minute bucket.
    """
    _require_api(api_id, session)
    return TimeseriesResponse(
        api_id=api_id,
        endpoint=endpoint,
        metric="errors.rate_pct",
        points=queries.error_series(session, api_id, window_min, endpoint, since),
    )


@router.get(
    "/health",
    response_model=HealthScoreResponse,
    summary="Composite health score for one API",
    responses=_NOT_FOUND,
)
def health_score(
    api_id: ApiIdParam, session: SessionDep, window_min: WindowParam = 60
) -> HealthScoreResponse:
    """Return a 0-100 health score blending availability and latency vs SLO.

    Args:
        api_id: Registry id of the API.
        session: Active database session.
        window_min: Look-back window in minutes.

    Returns:
        HealthScoreResponse: The score and the inputs behind it.
    """
    return queries.api_health(session, _require_api(api_id, session), window_min)


@router.get(
    "/summary",
    response_model=SummaryResponse,
    summary="Fleet-wide summary tiles",
)
def summary(session: SessionDep, window_min: WindowParam = 60) -> SummaryResponse:
    """Return fleet-wide totals for the dashboard header tiles.

    Args:
        session: Active database session.
        window_min: Look-back window in minutes.

    Returns:
        SummaryResponse: Totals across every registered API.
    """
    return queries.fleet_summary(session, window_min)


@router.get(
    "/overview",
    response_model=OverviewResponse,
    summary="Fleet tiles plus every API's current standing",
)
def overview(session: SessionDep, window_min: WindowParam = 60) -> OverviewResponse:
    """Return the whole dashboard header in one round trip.

    Args:
        session: Active database session.
        window_min: Look-back window in minutes.

    Returns:
        OverviewResponse: Fleet tiles and per-API rows, worst score first.
    """
    return OverviewResponse(
        window_min=window_min,
        generated_at=utcnow(),
        summary=queries.fleet_summary(session, window_min),
        apis=queries.api_overview(session, window_min),
    )


@router.get(
    "/endpoints",
    response_model=EndpointBreakdownResponse,
    summary="Per-endpoint Golden Signals for one API",
    responses=_NOT_FOUND,
)
def endpoints(
    api_id: ApiIdParam,
    session: SessionDep,
    window_min: WindowParam = 60,
    limit: Annotated[int, Query(ge=1, le=200, description="Maximum endpoints.")] = 50,
) -> EndpointBreakdownResponse:
    """Return one row per endpoint, slowest first.

    Args:
        api_id: Registry id of the API.
        session: Active database session.
        window_min: Look-back window in minutes.
        limit: Maximum number of endpoints to return.

    Returns:
        EndpointBreakdownResponse: The endpoint table for the window.
    """
    _require_api(api_id, session)
    return queries.endpoint_breakdown(session, api_id, window_min, limit)


@router.get(
    "/health-timeline",
    response_model=HealthTimelineResponse,
    summary="Composite health score history for one API",
    responses=_NOT_FOUND,
)
def health_timeline(
    api_id: ApiIdParam, session: SessionDep, window_min: WindowParam = 60
) -> HealthTimelineResponse:
    """Return one API's health score per minute bucket, for an up/down timeline.

    Args:
        api_id: Registry id of the API.
        session: Active database session.
        window_min: Look-back window in minutes.

    Returns:
        HealthTimelineResponse: The score history for the window.
    """
    api = _require_api(api_id, session)
    return queries.health_timeline(session, api, window_min)


@router.get(
    "/heatmap",
    response_model=HeatmapResponse,
    summary="Request-volume heatmap (time x endpoint) for one API",
    responses=_NOT_FOUND,
)
def heatmap(
    api_id: ApiIdParam,
    session: SessionDep,
    window_min: WindowParam = 60,
    max_endpoints: Annotated[
        int, Query(ge=1, le=50, description="Cap on distinct endpoints, busiest first.")
    ] = 12,
) -> HeatmapResponse:
    """Return a (time bucket, endpoint) request-volume matrix for one API.

    Args:
        api_id: Registry id of the API.
        session: Active database session.
        window_min: Look-back window in minutes.
        max_endpoints: Cap on distinct endpoints included.

    Returns:
        HeatmapResponse: One cell per bucket/endpoint pair with traffic.
    """
    _require_api(api_id, session)
    return queries.request_heatmap(session, api_id, window_min, max_endpoints)
