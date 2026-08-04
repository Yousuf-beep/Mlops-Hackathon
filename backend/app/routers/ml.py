"""Machine-learning routes: traffic forecasting, anomaly feed and model metrics.

The heavy lifting happens on the scheduler (:mod:`app.jobs.ml_jobs`), which
writes ``forecast`` and ``alert`` rows. These routes are mostly readers, so a
dashboard refresh never blocks on a model fit.

``GET /v1/forecast/{api_id}`` is the exception: if the scheduler has not
produced a forecast yet — a cold start, or a freshly registered API — it fits
one inline rather than returning an empty chart. The fit is milliseconds on the
minute-resolution series it reads.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlmodel import Session, col, select

from app import analytics as queries
from app.database import get_session
from app.jobs.ml_jobs import load_rollups
from app.ml import metrics_store
from app.ml.forecasting import build_series, fit_forecast
from app.models import Alert, ApiRegistry, Forecast, utcnow
from app.schemas import (
    AnomalyRead,
    ErrorResponse,
    ForecastPoint,
    ForecastResponse,
    ModelMetrics,
)

router = APIRouter(prefix="/v1", tags=["ml"])

SessionDep = Annotated[Session, Depends(get_session)]
ApiIdPath = Annotated[int, Path(description="Registry id of the API.")]

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
    "/forecast/{api_id}",
    response_model=ForecastResponse,
    summary="Forecast near-term traffic for one API",
    responses=_NOT_FOUND,
)
def forecast(
    api_id: ApiIdPath,
    session: SessionDep,
    horizon_min: Annotated[int, Query(ge=1, le=240, description="Minutes ahead.")] = 60,
) -> ForecastResponse:
    """Return a traffic forecast with 95% prediction intervals.

    Args:
        api_id: Registry id of the API.
        session: Active database session.
        horizon_min: How many minutes ahead to forecast.

    Returns:
        ForecastResponse: Stored points when the scheduler has produced them,
        otherwise a freshly fitted forecast.
    """
    _require_api(api_id, session)

    stored = session.exec(
        select(Forecast)
        .where(col(Forecast.api_id) == api_id, col(Forecast.horizon_min) <= horizon_min)
        .order_by(col(Forecast.horizon_min))
    ).all()

    if stored:
        return ForecastResponse(
            api_id=api_id,
            generated_at=stored[0].generated_at,
            points=[
                ForecastPoint(
                    horizon_min=row.horizon_min,
                    yhat=row.yhat,
                    yhat_lower=row.yhat_lower,
                    yhat_upper=row.yhat_upper,
                )
                for row in stored
            ],
        )

    result = fit_forecast(
        build_series(load_rollups(session, api_id, window_min=1440)), horizon_min=horizon_min
    )
    return ForecastResponse(
        api_id=api_id,
        generated_at=result.generated_at,
        points=[
            ForecastPoint(horizon_min=h, yhat=y, yhat_lower=low, yhat_upper=high)
            for h, y, low, high in zip(
                result.horizons, result.yhat, result.yhat_lower, result.yhat_upper, strict=True
            )
        ],
    )


@router.get(
    "/anomalies/{api_id}",
    response_model=list[AnomalyRead],
    summary="List detected anomalies for one API",
    responses=_NOT_FOUND,
)
def anomalies(
    api_id: ApiIdPath,
    session: SessionDep,
    window_min: Annotated[int, Query(ge=1, le=1440, description="Look-back minutes.")] = 240,
    limit: Annotated[int, Query(ge=1, le=200, description="Maximum alerts.")] = 50,
) -> list[AnomalyRead]:
    """Return anomalies detected in the recent window, newest first.

    Args:
        api_id: Registry id of the API.
        session: Active database session.
        window_min: Look-back window in minutes.
        limit: Maximum number of alerts to return.

    Returns:
        list[AnomalyRead]: Alerts raised in the window, newest first.
    """
    _require_api(api_id, session)
    since = utcnow() - timedelta(minutes=window_min)
    statement = (
        select(Alert)
        .where(col(Alert.api_id) == api_id, col(Alert.fired_at) >= since)
        .order_by(col(Alert.fired_at).desc())
        .limit(limit)
    )
    return queries.anomaly_reads(session, list(session.exec(statement).all()))


@router.get(
    "/alerts",
    response_model=list[AnomalyRead],
    summary="Fleet-wide alert feed, newest first",
)
def alerts(
    session: SessionDep,
    window_min: Annotated[int, Query(ge=1, le=1440, description="Look-back minutes.")] = 240,
    limit: Annotated[int, Query(ge=1, le=200, description="Maximum alerts.")] = 50,
    open_only: Annotated[bool, Query(description="Exclude alerts that already cleared.")] = False,
) -> list[AnomalyRead]:
    """Return the fleet's recent alerts for the dashboard's incident panel.

    Args:
        session: Active database session.
        window_min: Look-back window in minutes.
        limit: Maximum number of alerts to return.
        open_only: When true, only alerts that are still firing.

    Returns:
        list[AnomalyRead]: Alerts across every API, newest first.
    """
    since = utcnow() - timedelta(minutes=window_min)
    statement = select(Alert).where(col(Alert.fired_at) >= since)
    if open_only:
        statement = statement.where(col(Alert.resolved_at).is_(None))
    statement = statement.order_by(col(Alert.fired_at).desc()).limit(limit)
    return queries.anomaly_reads(session, list(session.exec(statement).all()))


@router.get(
    "/models/metrics",
    response_model=list[ModelMetrics],
    summary="Offline evaluation metrics for the deployed models",
)
def model_metrics() -> list[ModelMetrics]:
    """Return the last recorded evaluation metrics per model.

    Returns:
        list[ModelMetrics]: One entry per model that has reported since the
        process started, ordered by name. Empty until the first refit runs.
    """
    return metrics_store.snapshot()
