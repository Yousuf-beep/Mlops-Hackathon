"""Golden-Signal analytics routes (latency, traffic, errors, health, summary).

Phase 1 ships the contracts only. In phase 2 every handler here reads
exclusively from ``metric_rollup`` — never from ``request_log`` — which is the
whole point of the raw-log/rollup split described in :mod:`app.models`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.routers import NOT_IMPLEMENTED_RESPONSE, not_implemented
from app.schemas import HealthScoreResponse, SummaryResponse, TimeseriesResponse

router = APIRouter(prefix="/v1/analytics", tags=["analytics"])

WindowParam = Annotated[int, Query(ge=1, le=1440, description="Look-back window in minutes.")]
ApiIdParam = Annotated[int, Query(description="Registry id of the API to query.")]
EndpointParam = Annotated[str | None, Query(description="Restrict to one endpoint template.")]


@router.get(
    "/latency",
    response_model=TimeseriesResponse,
    summary="Latency percentiles over a window (phase 2)",
    responses=NOT_IMPLEMENTED_RESPONSE,
)
def latency(
    api_id: ApiIdParam,
    window_min: WindowParam = 60,
    endpoint: EndpointParam = None,
    percentile: Annotated[str, Query(pattern="^(p50|p95|p99|avg)$")] = "p95",
) -> TimeseriesResponse:
    """Return a latency percentile series from ``metric_rollup``.

    Args:
        api_id: Registry id of the API.
        window_min: Look-back window in minutes.
        endpoint: Optional endpoint filter.
        percentile: Which latency column to project.

    Raises:
        HTTPException: Always 501 in phase 1.
    """
    raise not_implemented("analytics.latency")


@router.get(
    "/traffic",
    response_model=TimeseriesResponse,
    summary="Request-rate series over a window (phase 2)",
    responses=NOT_IMPLEMENTED_RESPONSE,
)
def traffic(
    api_id: ApiIdParam,
    window_min: WindowParam = 60,
    endpoint: EndpointParam = None,
) -> TimeseriesResponse:
    """Return the requests-per-minute series from ``metric_rollup``.

    Args:
        api_id: Registry id of the API.
        window_min: Look-back window in minutes.
        endpoint: Optional endpoint filter.

    Raises:
        HTTPException: Always 501 in phase 1.
    """
    raise not_implemented("analytics.traffic")


@router.get(
    "/errors",
    response_model=TimeseriesResponse,
    summary="Error-rate series over a window (phase 2)",
    responses=NOT_IMPLEMENTED_RESPONSE,
)
def errors(
    api_id: ApiIdParam,
    window_min: WindowParam = 60,
    endpoint: EndpointParam = None,
) -> TimeseriesResponse:
    """Return the error-rate series from ``metric_rollup``.

    Args:
        api_id: Registry id of the API.
        window_min: Look-back window in minutes.
        endpoint: Optional endpoint filter.

    Raises:
        HTTPException: Always 501 in phase 1.
    """
    raise not_implemented("analytics.errors")


@router.get(
    "/health",
    response_model=HealthScoreResponse,
    summary="Composite health score for one API (phase 2)",
    responses=NOT_IMPLEMENTED_RESPONSE,
)
def health_score(api_id: ApiIdParam, window_min: WindowParam = 60) -> HealthScoreResponse:
    """Return a 0-100 health score blending availability and latency vs SLO.

    Args:
        api_id: Registry id of the API.
        window_min: Look-back window in minutes.

    Raises:
        HTTPException: Always 501 in phase 1.
    """
    raise not_implemented("analytics.health")


@router.get(
    "/summary",
    response_model=SummaryResponse,
    summary="Fleet-wide summary tiles (phase 2)",
    responses=NOT_IMPLEMENTED_RESPONSE,
)
def summary(window_min: WindowParam = 60) -> SummaryResponse:
    """Return fleet-wide totals for the dashboard header tiles.

    Args:
        window_min: Look-back window in minutes.

    Raises:
        HTTPException: Always 501 in phase 1.
    """
    raise not_implemented("analytics.summary")
