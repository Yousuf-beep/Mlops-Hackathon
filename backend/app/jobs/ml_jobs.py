"""Scheduled ML work: anomaly detection and forecast refits.

Both jobs read ``metric_rollup``, run the pure functions in :mod:`app.ml`, and
write their conclusions back as ``alert`` / ``forecast`` rows. Keeping the
models pure and the persistence here means the detectors can be unit-tested on
a DataFrame with no database in sight.

Alert lifecycle
---------------
An alert is raised once per (api, signal) and stays *open* until the signal
comes back inside its band, at which point the job stamps ``resolved_at``.
Without that, a five-minute incident would produce five identical alerts and
the dashboard's "open alerts" tile would only ever climb.

Detection is API-wide rather than per-endpoint: the detectors baseline against
the API's aggregate signal, so ``alert.endpoint`` is left null. Per-endpoint
detection is a natural extension — group the rollups by endpoint before
scoring — but it multiplies the alert volume, which needs a suppression policy
this does not yet have.
"""

from __future__ import annotations

import logging
from datetime import timedelta

import pandas as pd
from sqlmodel import Session, col, select

from app.config import settings
from app.database import engine
from app.events import mark_dirty
from app.ml import metrics_store
from app.ml.anomaly import AnomalyResult, detect, explain
from app.ml.forecasting import backtest, build_series, fit_forecast
from app.models import (
    Alert,
    AlertSeverity,
    AlertType,
    ApiRegistry,
    Forecast,
    MetricRollup,
    utcnow,
)

logger = logging.getLogger(__name__)

#: Rollup columns pulled into the detector's DataFrame.
_ROLLUP_COLUMNS = ("bucket", "endpoint", "req_count", "err_count", "p95_ms", "saturation_pct")


def load_rollups(session: Session, api_id: int, window_min: int) -> pd.DataFrame:
    """Read one API's recent rollups into a DataFrame.

    Args:
        session: Active database session.
        api_id: Registry id of the API.
        window_min: Look-back window in minutes.

    Returns:
        pd.DataFrame: Columns :data:`_ROLLUP_COLUMNS`, ascending by bucket.
        Empty when the API has no rollups in the window.
    """
    since = utcnow() - timedelta(minutes=window_min)
    rows = session.exec(
        select(MetricRollup)
        .where(col(MetricRollup.api_id) == api_id, col(MetricRollup.bucket) >= since)
        .order_by(col(MetricRollup.bucket))
    ).all()
    if not rows:
        return pd.DataFrame(columns=list(_ROLLUP_COLUMNS))
    return pd.DataFrame(
        [{column: getattr(row, column) for column in _ROLLUP_COLUMNS} for row in rows]
    )


def _open_alerts(session: Session, api_id: int) -> dict[str, Alert]:
    """Index an API's currently firing alerts by signal.

    Args:
        session: Active database session.
        api_id: Registry id of the API.

    Returns:
        dict[str, Alert]: ``signal`` → the open alert for it.
    """
    rows = session.exec(
        select(Alert).where(col(Alert.api_id) == api_id, col(Alert.resolved_at).is_(None))
    ).all()
    return {alert.signal: alert for alert in rows}


def _persist(session: Session, api: ApiRegistry, findings: list[AnomalyResult]) -> int:
    """Raise new alerts and resolve ones whose signal recovered.

    Args:
        session: Active database session.
        api: The API the findings belong to.
        findings: Detections for the newest bucket.

    Returns:
        int: Number of alerts newly raised.
    """
    open_alerts = _open_alerts(session, api.id or 0)
    firing = {finding.signal for finding in findings}
    raised = 0

    for finding in findings:
        if finding.signal in open_alerts:
            continue  # already firing; do not duplicate
        session.add(
            Alert(
                api_id=api.id or 0,
                endpoint=None,
                type=AlertType.ANOMALY,
                severity=AlertSeverity(finding.severity),
                signal=finding.signal,
                explanation=explain(finding, api.name, None),
                metric_value=finding.metric_value,
                expected_range=f"{finding.expected_low:.1f}-{finding.expected_high:.1f}",
                confidence=finding.confidence,
            )
        )
        raised += 1

    for signal, alert in open_alerts.items():
        if signal not in firing:
            alert.resolved_at = utcnow()
            session.add(alert)

    session.commit()
    return raised


def run_anomaly_detection(session: Session, window_min: int | None = None) -> int:
    """Score every registered API's newest bucket and record the findings.

    Args:
        session: Active database session.
        window_min: Look-back window the detectors baseline against. Defaults
            to ``settings.ANOMALY_WINDOW_MINUTES``.

    Returns:
        int: Number of alerts raised across the fleet.
    """
    window = window_min or settings.ANOMALY_WINDOW_MINUTES
    raised = 0
    for api in session.exec(select(ApiRegistry)).all():
        rollups = load_rollups(session, api.id or 0, window)
        findings = detect(rollups, slo_latency_ms=api.slo_latency_ms)
        raised += _persist(session, api, findings)
    if raised:
        # The detectors are unsupervised, so there is no labelled precision or
        # recall to report; the fire count is the honest observable.
        metrics_store.record("anomaly_ensemble", {})
    return raised


def run_forecasts(session: Session, horizon_min: int | None = None) -> int:
    """Refit the traffic forecast for every registered API.

    Each refit replaces that API's previous points rather than appending: the
    forecast table answers "what do we expect next?", and keeping every
    superseded generation would make that query grow without bound.

    Args:
        session: Active database session.
        horizon_min: Minutes ahead to predict. Defaults to
            ``settings.FORECAST_HORIZON_MINUTES``.

    Returns:
        int: Number of APIs whose forecast was refreshed.
    """
    horizon = horizon_min or settings.FORECAST_HORIZON_MINUTES
    refreshed = 0

    for api in session.exec(select(ApiRegistry)).all():
        rollups = load_rollups(session, api.id or 0, window_min=1440)
        series = build_series(rollups)
        if series.empty:
            continue

        result = fit_forecast(series, horizon_min=horizon)
        for stale in session.exec(select(Forecast).where(col(Forecast.api_id) == api.id)).all():
            session.delete(stale)
        session.add_all(
            [
                Forecast(
                    api_id=api.id or 0,
                    endpoint=None,
                    generated_at=result.generated_at,
                    horizon_min=horizon_offset,
                    yhat=yhat,
                    yhat_lower=lower,
                    yhat_upper=upper,
                )
                for horizon_offset, yhat, lower, upper in zip(
                    result.horizons,
                    result.yhat,
                    result.yhat_lower,
                    result.yhat_upper,
                    strict=True,
                )
            ]
        )
        refreshed += 1

        # Scored on a short horizon: a 60-minute backtest needs 5 hours of
        # history before it yields even one fold, and the panel should show
        # real numbers within minutes of a cold start.
        scores = backtest(series, horizon_min=min(horizon, 15), folds=3)
        if scores["folds"]:
            metrics_store.record(result.model_name, scores)
            metrics_store.record(
                "seasonal_naive",
                {
                    "mae": scores["mae_baseline"],
                    "rmse": scores["rmse_baseline"],
                    "mape": scores["mape_baseline"],
                },
            )

    session.commit()
    return refreshed


def anomaly_job() -> None:
    """Scheduler entry point for anomaly detection.

    Exceptions are logged, not raised: a failed tick must not kill the
    scheduler thread and silence every later tick.
    """
    try:
        with Session(engine) as session:
            raised = run_anomaly_detection(session)
        if raised:
            logger.info("anomaly job raised %d alert(s)", raised)
        # Bump unconditionally, not just when a new alert fired: a resolved
        # alert also changes the fleet's open-alert count and per-API status.
        mark_dirty()
    except Exception:
        logger.exception("anomaly job failed")


def forecast_job() -> None:
    """Scheduler entry point for the forecast refit."""
    try:
        with Session(engine) as session:
            refreshed = run_forecasts(session)
        if refreshed:
            logger.info("forecast job refreshed %d api(s)", refreshed)
            mark_dirty()
    except Exception:
        logger.exception("forecast job failed")
