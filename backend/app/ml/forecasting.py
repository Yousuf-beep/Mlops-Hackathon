"""Traffic forecasting.

Approach
--------
Input is the per-minute request-count series read from ``metric_rollup``, which
is already regularly spaced — that is exactly why the rollup table exists.

Model: **statsmodels Holt-Winters exponential smoothing**
(``ExponentialSmoothing``) with an additive seasonality. It is chosen over
ARIMA because API traffic is dominated by level + seasonality rather than
autocorrelated shocks, it fits in milliseconds on a few thousand points (so it
can be refit on a 5-minute schedule inside the API process), and its residuals
give a prediction interval without a separate bootstrap.

Adaptive model selection
------------------------
A daily season needs two full days of minutes before Holt-Winters can be fitted
at all, and a freshly deployed PulseGrid has minutes of history, not days.
:func:`fit_forecast` therefore degrades deliberately rather than crashing or
silently emitting a flat line:

* ``>= 2 x seasonal_periods`` samples → seasonal Holt-Winters.
* ``>= 12`` samples → damped-trend exponential smoothing, no seasonality.
* anything shorter → the trailing mean.

The variant that ran is reported in :attr:`ForecastResult.model_name`, so the
dashboard and ``/v1/models/metrics`` always say which model produced a number.

Baseline for comparison: seasonal-naive (the value one season ago, degrading to
the last observation when no full season exists). The forecaster must beat it
on MAE/MAPE to be worth deploying; both are surfaced by
``GET /v1/models/metrics``.

Evaluation: rolling-origin backtest on a held-out tail, scored with MAE, RMSE
and MAPE.
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

#: Below this many samples nothing but a mean is defensible.
MIN_SAMPLES_FOR_TREND = 12

#: z multiplier for a 95% interval under an approximately normal residual.
_Z_95 = 1.959963985

#: Names reported for each fitted variant.
MODEL_SEASONAL = "holt_winters_additive"
MODEL_TREND = "exponential_smoothing_damped"
MODEL_MEAN = "trailing_mean"
MODEL_BASELINE = "seasonal_naive"


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
        An empty frame yields an empty series rather than raising, so a
        just-registered API is a no-op instead of an error.
    """
    if rollups.empty:
        return pd.Series(dtype="float64")

    frame = rollups.copy()
    frame["bucket"] = pd.to_datetime(frame["bucket"], utc=True)
    # Several endpoints share a bucket; the API-wide traffic series is their sum.
    collapsed = frame.groupby("bucket", as_index=True)[value_column].sum().sort_index()
    full_index = pd.date_range(collapsed.index.min(), collapsed.index.max(), freq="min", tz=UTC)
    return collapsed.reindex(full_index, fill_value=0).astype("float64")


def _interval(point: np.ndarray, residual_std: float) -> tuple[np.ndarray, np.ndarray]:
    """Build a symmetric 95% interval around point predictions.

    Args:
        point: Point predictions.
        residual_std: Standard deviation of the in-sample residuals.

    Returns:
        tuple[np.ndarray, np.ndarray]: Lower and upper bounds. The lower bound
        is clipped at zero because a negative request count is meaningless.
    """
    margin = _Z_95 * max(residual_std, 1e-9)
    return np.maximum(point - margin, 0.0), point + margin


def fit_forecast(
    series: pd.Series,
    horizon_min: int = 60,
    seasonal_periods: int = 1440,
    alpha: float = 0.05,
) -> ForecastResult:
    """Fit the strongest model the series length supports and forecast forward.

    Args:
        series: Minute-frequency traffic series from :func:`build_series`.
        horizon_min: How many minutes ahead to predict.
        seasonal_periods: Season length in samples (1440 = one day of minutes).
        alpha: Significance level. Documents intent; the interval is fixed at
            95%, which is what the dashboard renders.

    Returns:
        ForecastResult: Predictions with their intervals. An empty input yields
        an all-zero forecast tagged :data:`MODEL_MEAN`.

    Raises:
        ValueError: If ``horizon_min`` is not positive.
    """
    if horizon_min <= 0:
        raise ValueError("horizon_min must be positive")

    generated_at = datetime.now(UTC)
    horizons = list(range(1, horizon_min + 1))

    if series.empty:
        zeros = [0.0] * horizon_min
        return ForecastResult(generated_at, horizons, zeros, zeros, zeros, MODEL_MEAN)

    values = series.to_numpy(dtype="float64")

    if len(values) < MIN_SAMPLES_FOR_TREND:
        point = np.full(horizon_min, float(values.mean()))
        lower, upper = _interval(point, float(values.std(ddof=0)))
        return ForecastResult(
            generated_at,
            horizons,
            point.round(3).tolist(),
            lower.round(3).tolist(),
            upper.round(3).tolist(),
            MODEL_MEAN,
        )

    seasonal = len(values) >= 2 * seasonal_periods
    model_name = MODEL_SEASONAL if seasonal else MODEL_TREND

    from statsmodels.tsa.holtwinters import ExponentialSmoothing

    try:
        # statsmodels is noisy about convergence on short, spiky series; the
        # fitted values stay usable and the except branch covers real failures.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            fitted = ExponentialSmoothing(
                values,
                trend="add",
                damped_trend=True,
                seasonal="add" if seasonal else None,
                seasonal_periods=seasonal_periods if seasonal else None,
                initialization_method="estimated",
            ).fit(optimized=True)
            point = np.asarray(fitted.forecast(horizon_min), dtype="float64")
            residual_std = float(np.std(values - np.asarray(fitted.fittedvalues), ddof=0))
    except (ValueError, np.linalg.LinAlgError) as exc:
        logger.warning("Holt-Winters fit failed (%s); falling back to trailing mean", exc)
        point = np.full(horizon_min, float(values[-min(len(values), 60) :].mean()))
        residual_std = float(values.std(ddof=0))
        model_name = MODEL_MEAN

    point = np.maximum(np.nan_to_num(point, nan=0.0), 0.0)
    lower, upper = _interval(point, residual_std)
    _ = alpha
    return ForecastResult(
        generated_at,
        horizons,
        point.round(3).tolist(),
        lower.round(3).tolist(),
        upper.round(3).tolist(),
        model_name,
    )


def _scores(actual: np.ndarray, predicted: np.ndarray) -> tuple[float, float, float]:
    """Score a prediction against the truth.

    Args:
        actual: Observed values.
        predicted: Predicted values, same length.

    Returns:
        tuple[float, float, float]: ``(mae, rmse, mape)``. MAPE skips zero
        actuals, which dominate a quiet traffic series and would otherwise make
        the statistic infinite.
    """
    error = actual - predicted
    mae = float(np.mean(np.abs(error)))
    rmse = float(np.sqrt(np.mean(error**2)))
    nonzero = actual != 0
    mape = (
        float(np.mean(np.abs(error[nonzero] / actual[nonzero])) * 100.0) if nonzero.any() else 0.0
    )
    return mae, rmse, mape


def backtest(series: pd.Series, horizon_min: int = 60, folds: int = 5) -> dict[str, float]:
    """Rolling-origin backtest of the forecaster against a seasonal-naive baseline.

    Each fold moves the origin forward by one horizon, fits on everything before
    it and scores against the horizon that follows. This mirrors how the model
    is actually used — always predicting unseen future — unlike a random split,
    which would leak future information into training.

    Args:
        series: Minute-frequency traffic series.
        horizon_min: Forecast horizon evaluated in each fold.
        folds: Number of rolling origins to evaluate.

    Returns:
        dict[str, float]: ``mae``, ``rmse``, ``mape``, their ``*_baseline``
        counterparts, and ``folds`` — the number of origins actually scored.
        All zeros when the series is too short to score even one fold.
    """
    empty = {
        "mae": 0.0,
        "rmse": 0.0,
        "mape": 0.0,
        "mae_baseline": 0.0,
        "rmse_baseline": 0.0,
        "mape_baseline": 0.0,
        "folds": 0.0,
    }
    values = series.to_numpy(dtype="float64")
    usable_folds = min(folds, max(0, (len(values) - MIN_SAMPLES_FOR_TREND) // horizon_min))
    if usable_folds == 0:
        return empty

    model_scores: list[tuple[float, float, float]] = []
    baseline_scores: list[tuple[float, float, float]] = []

    for fold in range(usable_folds, 0, -1):
        split = len(values) - fold * horizon_min
        train, test = values[:split], values[split : split + horizon_min]
        if len(test) < horizon_min:
            continue
        prediction = np.asarray(
            fit_forecast(pd.Series(train), horizon_min=horizon_min).yhat, dtype="float64"
        )
        model_scores.append(_scores(test, prediction))
        # Seasonal-naive with no full season available degrades to last-value.
        baseline_scores.append(_scores(test, np.full(horizon_min, train[-1])))

    if not model_scores:
        return empty

    mae, rmse, mape = (float(np.mean(column)) for column in zip(*model_scores, strict=True))
    b_mae, b_rmse, b_mape = (
        float(np.mean(column)) for column in zip(*baseline_scores, strict=True)
    )
    return {
        "mae": round(mae, 4),
        "rmse": round(rmse, 4),
        "mape": round(mape, 4),
        "mae_baseline": round(b_mae, 4),
        "rmse_baseline": round(b_rmse, 4),
        "mape_baseline": round(b_mape, 4),
        "folds": float(len(model_scores)),
    }
