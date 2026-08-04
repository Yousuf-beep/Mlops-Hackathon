"""Traffic forecasting (phase 3 — signatures only).

Planned approach
----------------
Input is the per-minute request count series read from ``metric_rollup``, which
is already regularly spaced — that is exactly why the rollup table exists.

Model: **statsmodels Holt-Winters exponential smoothing**
(``ExponentialSmoothing``) with an additive daily seasonality. It is chosen
over ARIMA because API traffic is dominated by level + seasonality rather than
autocorrelated shocks, it fits in milliseconds on a few thousand points (so it
can be refit on a 5-minute schedule inside the API process), and it produces
prediction intervals without a separate bootstrap.

Baseline for comparison: seasonal-naive (value from 24 h ago). The forecaster
must beat it on MAE/MAPE to be worth deploying; both numbers are surfaced by
``GET /v1/models/metrics``.

Evaluation: rolling-origin backtest on a held-out tail of the series, scored
with MAE, RMSE and MAPE.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd


@dataclass(frozen=True, slots=True)
class ForecastResult:
    """Output of a single forecasting run.

    Attributes:
        generated_at: When the fit was produced (UTC).
        horizons: Minutes-ahead offsets, aligned with the value arrays.
        yhat: Point predictions, one per horizon.
        yhat_lower: Lower bound of the prediction interval.
        yhat_upper: Upper bound of the prediction interval.
        model_name: Identifier of the fitted model, for the metrics endpoint.
    """

    generated_at: datetime
    horizons: list[int]
    yhat: list[float]
    yhat_lower: list[float]
    yhat_upper: list[float]
    model_name: str


def build_series(rollups: pd.DataFrame, value_column: str = "req_count") -> pd.Series:
    """Turn rollup rows into a gap-free, minute-indexed series.

    Args:
        rollups: Rows from ``metric_rollup``, with at least ``bucket`` and
            ``value_column`` columns.
        value_column: Which metric column to forecast.

    Returns:
        pd.Series: A minute-frequency series with missing buckets filled with
        zero, since "no rows in the bucket" means "no traffic", not "unknown".

    Raises:
        NotImplementedError: Phase 3.
    """
    raise NotImplementedError("phase 3: forecasting.build_series")


def fit_forecast(
    series: pd.Series,
    horizon_min: int = 60,
    seasonal_periods: int = 1440,
    alpha: float = 0.05,
) -> ForecastResult:
    """Fit Holt-Winters on the series and forecast forward.

    Args:
        series: Minute-frequency traffic series from :func:`build_series`.
        horizon_min: How many minutes ahead to predict.
        seasonal_periods: Season length in samples (1440 = one day of minutes).
        alpha: Significance level; ``0.05`` yields a 95% prediction interval.

    Returns:
        ForecastResult: Predictions with their intervals.

    Raises:
        NotImplementedError: Phase 3.
    """
    raise NotImplementedError("phase 3: forecasting.fit_forecast")


def backtest(series: pd.Series, horizon_min: int = 60, folds: int = 5) -> dict[str, float]:
    """Rolling-origin backtest of the forecaster against a seasonal-naive baseline.

    Args:
        series: Minute-frequency traffic series.
        horizon_min: Forecast horizon evaluated in each fold.
        folds: Number of rolling origins to evaluate.

    Returns:
        dict[str, float]: ``mae``, ``rmse``, ``mape`` plus the ``*_baseline``
        equivalents for the seasonal-naive comparison.

    Raises:
        NotImplementedError: Phase 3.
    """
    raise NotImplementedError("phase 3: forecasting.backtest")
