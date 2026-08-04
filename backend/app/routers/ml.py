"""Machine-learning routes: traffic forecasting, anomaly feed and model metrics.

Phase 1 ships the contracts only. Phase 3 backs them with the implementations
sketched in :mod:`app.ml.forecasting` and :mod:`app.ml.anomaly`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Query

from app.routers import NOT_IMPLEMENTED_RESPONSE, not_implemented
from app.schemas import AnomalyRead, ForecastResponse, ModelMetrics

router = APIRouter(prefix="/v1", tags=["ml"])

ApiIdPath = Annotated[int, Path(description="Registry id of the API.")]


@router.get(
    "/forecast/{api_id}",
    response_model=ForecastResponse,
    summary="Forecast near-term traffic for one API (phase 3)",
    responses=NOT_IMPLEMENTED_RESPONSE,
)
def forecast(
    api_id: ApiIdPath,
    horizon_min: Annotated[int, Query(ge=1, le=240, description="Minutes ahead.")] = 60,
) -> ForecastResponse:
    """Return a traffic forecast with prediction intervals.

    Args:
        api_id: Registry id of the API.
        horizon_min: How many minutes ahead to forecast.

    Raises:
        HTTPException: Always 501 in phase 1.
    """
    raise not_implemented("ml.forecast")


@router.get(
    "/anomalies/{api_id}",
    response_model=list[AnomalyRead],
    summary="List detected anomalies for one API (phase 3)",
    responses=NOT_IMPLEMENTED_RESPONSE,
)
def anomalies(
    api_id: ApiIdPath,
    window_min: Annotated[int, Query(ge=1, le=1440, description="Look-back minutes.")] = 240,
) -> list[AnomalyRead]:
    """Return anomalies detected in the recent window, newest first.

    Args:
        api_id: Registry id of the API.
        window_min: Look-back window in minutes.

    Raises:
        HTTPException: Always 501 in phase 1.
    """
    raise not_implemented("ml.anomalies")


@router.get(
    "/models/metrics",
    response_model=list[ModelMetrics],
    summary="Offline evaluation metrics for the deployed models (phase 3)",
    responses=NOT_IMPLEMENTED_RESPONSE,
)
def model_metrics() -> list[ModelMetrics]:
    """Return the last recorded evaluation metrics per model.

    Raises:
        HTTPException: Always 501 in phase 1.
    """
    raise not_implemented("ml.model_metrics")
