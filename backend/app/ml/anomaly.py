"""Anomaly detection over Golden-Signal rollups.

Approach
--------
Two complementary detectors, because API incidents come in two shapes:

1. **Robust z-score on a rolling baseline** (per signal). Uses median and MAD
   rather than mean and standard deviation so a single spike does not inflate
   the baseline and mask the next one. Catches sudden univariate breaks — a
   latency cliff, an error burst.

2. **scikit-learn IsolationForest** over the joint feature vector
   ``(p95_ms, req_count, err_rate, saturation_pct)``. Catches *combinations*
   that are individually unremarkable but jointly abnormal — for example
   traffic collapsing while latency stays flat, which a per-signal detector
   never sees.

Every detection carries a natural-language ``explanation`` and the
``expected_range`` it violated, so the dashboard can answer "why did this fire?"
rather than only "something fired".

Only the **most recent** bucket is reported. The detectors score the whole
window because they need the history to form a baseline, but alerting on old
buckets on every run would re-fire the same incident once a minute.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

#: Scale factor turning a MAD into a standard-deviation-equivalent, so the
#: threshold below is interpretable in familiar sigma units.
_MAD_TO_SIGMA = 0.6745

#: Robust z above which a point is anomalous. 3.5 is the Iglewicz-Hoaglin
#: recommendation and is deliberately less trigger-happy than the classic 3.0.
DEFAULT_Z_THRESHOLD = 3.5

#: Last-resort spread for a perfectly constant baseline, as a fraction of its
#: level: a 1% move off a dead-flat series reads as one sigma.
_FLAT_BASELINE_SCALE = 0.01

#: Minimum samples before a rolling baseline means anything. Below this the
#: detector stays silent rather than calling the second data point an anomaly.
MIN_BASELINE_SAMPLES = 8

#: Multiples of the threshold at which severity escalates.
_CRITICAL_MULTIPLE = 2.0
_WARNING_MULTIPLE = 1.0

#: Per-detector scale for turning a raw score into a 0-1 confidence, chosen so
#: a score right at the firing threshold reads as ~50% confident and climbs
#: towards (but never reaches) 100% for increasingly extreme scores. The two
#: detectors report scores on unrelated scales (sigma units vs. an
#: IsolationForest decision function), so each gets its own scale rather than
#: one constant that would misread as over- or under-confident for the other.
_CONFIDENCE_SCALE = {"robust_zscore": DEFAULT_Z_THRESHOLD, "isolation_forest": 0.15}


def confidence_from_score(score: float, detector: str) -> float:
    """Squash a detector score into an operator-facing 0-1 confidence.

    This is a monotonic heuristic, not a calibrated probability: neither
    detector is trained against labelled incidents, so there is nothing to
    calibrate against. It exists so the dashboard can show *how* anomalous a
    finding is at a glance, on top of the ``severity`` bucket it already gets.

    Args:
        score: The detector's own score (already computed for severity and
            the explanation text — this reuses it rather than adding a second
            signal).
        detector: Which detector produced the score, selecting its scale.

    Returns:
        float: Confidence in ``[0, 0.99]``, rounded to 3 places.
    """
    scale = _CONFIDENCE_SCALE.get(detector, DEFAULT_Z_THRESHOLD)
    magnitude = abs(score)
    return round(min(0.99, magnitude / (magnitude + scale)), 3)

#: Human-facing units per signal, used when rendering explanations.
_UNITS = {
    "latency": "ms",
    "traffic": "req/min",
    "errors": "%",
    "saturation": "%",
    "multivariate": "ms",
}


@dataclass(frozen=True, slots=True)
class AnomalyResult:
    """One detected anomaly, ready to be persisted as an ``alert`` row.

    Attributes:
        signal: Golden Signal involved (``latency``/``traffic``/``errors``/
            ``saturation``).
        metric_value: The observed value that triggered the detection.
        expected_low: Lower edge of the expected band.
        expected_high: Upper edge of the expected band.
        score: Detector score; higher means more anomalous.
        severity: ``info``, ``warning`` or ``critical``.
        explanation: Human-readable reason, rendered for the dashboard.
        detector: Which detector fired (``robust_zscore`` or
            ``isolation_forest``).
        confidence: 0-1 heuristic confidence, see :func:`confidence_from_score`.
    """

    signal: str
    metric_value: float
    expected_low: float
    expected_high: float
    score: float
    severity: str
    explanation: str
    detector: str
    confidence: float


def robust_zscore(series: pd.Series, window: int = 30, threshold: float = 3.5) -> pd.Series:
    """Score each point by its robust z-score against a trailing window.

    Uses ``0.6745 * (x - median) / MAD``, the standard MAD-based estimator. The
    baseline is *trailing and exclusive* — a point is never part of the window
    it is judged against, which stops a large spike from normalising itself.

    Args:
        series: Metric series indexed by minute bucket.
        window: Trailing baseline length in samples.
        threshold: Score above which a point counts as anomalous. Retained for
            call-site readability; the caller applies it.

    Returns:
        pd.Series: Robust z-scores aligned with the input index. Points without
        enough history score ``0.0`` — unknown is not the same as normal, but
        alerting on unknown is worse than staying quiet.
    """
    _ = threshold
    values = series.astype("float64")
    baseline = values.shift(1).rolling(window=window, min_periods=MIN_BASELINE_SAMPLES)
    median = baseline.median()
    mad = baseline.apply(lambda w: np.median(np.abs(w - np.median(w))), raw=True)

    # A MAD of zero means a perfectly flat baseline, where any deviation is
    # infinitely many MADs away. Degrade to the rolling standard deviation, and
    # if that is zero too, to a fraction of the level itself — so a synthetic or
    # rate-limited series that sits at exactly one value still produces a large
    # but *finite* score instead of an inf that no threshold can compare.
    scale = (
        (mad / _MAD_TO_SIGMA)
        .replace(0.0, np.nan)
        .fillna(baseline.std().replace(0.0, np.nan))
        .fillna(median.abs() * _FLAT_BASELINE_SCALE)
        .replace(0.0, np.nan)
    )

    scores = (values - median) / scale
    return scores.replace([np.inf, -np.inf], np.nan).fillna(0.0)


def fit_isolation_forest(features: pd.DataFrame, contamination: float = 0.02) -> object:
    """Fit an IsolationForest on multivariate Golden-Signal features.

    Args:
        features: Rows of ``(p95_ms, req_count, err_rate, saturation_pct)``.
        contamination: Expected proportion of anomalous rows.

    Returns:
        object: The fitted ``sklearn.ensemble.IsolationForest``.

    Raises:
        ValueError: If ``features`` is empty.
    """
    if features.empty:
        raise ValueError("cannot fit IsolationForest on an empty feature frame")

    from sklearn.ensemble import IsolationForest

    model = IsolationForest(
        n_estimators=128,
        contamination=contamination,
        # Fixed seed: an alert that appears and disappears between identical
        # runs is worse than a slightly suboptimal forest.
        random_state=42,
    )
    model.fit(features.to_numpy(dtype="float64"))
    return model


def _severity_for(score: float, threshold: float) -> str:
    """Grade a detector score into an operator-facing severity.

    Args:
        score: Absolute detector score.
        threshold: The score at which the detector fires at all.

    Returns:
        str: ``critical``, ``warning`` or ``info``.
    """
    if score >= threshold * _CRITICAL_MULTIPLE:
        return "critical"
    if score >= threshold * _WARNING_MULTIPLE:
        return "warning"
    return "info"


def explain(result: AnomalyResult, api_name: str, endpoint: str | None) -> str:
    """Render a one-sentence explanation for an anomaly.

    Args:
        result: The detection to describe.
        api_name: Human-readable API name.
        endpoint: Endpoint template, or ``None`` for API-wide.

    Returns:
        str: For example ``"p95 latency 812 ms on /orders (Payments API) is
        4.1 sigma above the recent baseline of 120-180 ms."``
    """
    unit = _UNITS.get(result.signal, "")
    scope = f"{endpoint} ({api_name})" if endpoint else api_name
    band = f"{result.expected_low:.1f}-{result.expected_high:.1f} {unit}".strip()
    direction = "above" if result.metric_value > result.expected_high else "below"

    if result.detector == "isolation_forest":
        return (
            f"{result.signal} on {scope} is jointly abnormal: the combination of "
            f"latency, traffic and error rate scores {result.score:.2f} against the "
            f"last window, outside the usual {band} band for this signal."
        )
    return (
        f"{result.signal} {result.metric_value:.1f} {unit}".rstrip()
        + f" on {scope} is {abs(result.score):.1f} sigma {direction} "
        f"the recent baseline of {band}."
    )


def _band(series: pd.Series, window: int, threshold: float) -> tuple[float, float]:
    """Compute the expected band for the newest point of a series.

    Args:
        series: The metric series being judged.
        window: Trailing baseline length.
        threshold: Robust-z threshold defining the band edges.

    Returns:
        tuple[float, float]: ``(low, high)``, clipped at zero below.
    """
    baseline = series.iloc[:-1].tail(window).astype("float64")
    if baseline.empty:
        return 0.0, 0.0
    median = float(baseline.median())
    mad = float(np.median(np.abs(baseline - median)))
    scale = mad / _MAD_TO_SIGMA if mad > 0 else float(baseline.std(ddof=0) or 0.0)
    return max(0.0, median - threshold * scale), median + threshold * scale


def detect(rollups: pd.DataFrame, slo_latency_ms: int = 500) -> list[AnomalyResult]:
    """Run both detectors over a window of rollups and merge their findings.

    Args:
        rollups: Recent rows from ``metric_rollup`` for one API, with ``bucket``,
            ``req_count``, ``err_count``, ``p95_ms`` and optionally
            ``saturation_pct``.
        slo_latency_ms: The API's latency objective. A latency anomaly that is
            still inside the SLO is reported as ``info`` — technically unusual,
            but not yet worth waking anybody.

    Returns:
        list[AnomalyResult]: Detections for the most recent bucket only,
        de-duplicated across detectors and ordered by descending score.
    """
    if rollups.empty:
        return []

    frame = rollups.copy()
    frame["bucket"] = pd.to_datetime(frame["bucket"], utc=True)
    aggregations: dict[str, tuple[str, str]] = {
        "req_count": ("req_count", "sum"),
        "err_count": ("err_count", "sum"),
        # The API-level latency signal takes the worst endpoint in the bucket:
        # one endpoint falling over is an incident even when the mean is calm.
        "p95_ms": ("p95_ms", "max"),
    }
    if "saturation_pct" in frame.columns and frame["saturation_pct"].notna().any():
        aggregations["saturation_pct"] = ("saturation_pct", "mean")
    grouped = frame.groupby("bucket").agg(**aggregations).sort_index()  # type: ignore[call-overload]
    if len(grouped) < MIN_BASELINE_SAMPLES + 1:
        return []

    grouped["err_rate"] = 100.0 * grouped["err_count"] / grouped["req_count"].replace(0, np.nan)
    grouped = grouped.fillna(0.0)

    signals = {
        "latency": grouped["p95_ms"],
        "traffic": grouped["req_count"].astype("float64"),
        "errors": grouped["err_rate"],
    }

    results: list[AnomalyResult] = []
    for signal, series in signals.items():
        scores = robust_zscore(series)
        score = float(scores.iloc[-1])
        if abs(score) < DEFAULT_Z_THRESHOLD:
            continue
        value = float(series.iloc[-1])
        low, high = _band(series, window=30, threshold=DEFAULT_Z_THRESHOLD)
        severity = _severity_for(abs(score), DEFAULT_Z_THRESHOLD)
        if signal == "latency" and value <= slo_latency_ms:
            severity = "info"
        results.append(
            AnomalyResult(
                signal=signal,
                metric_value=round(value, 3),
                expected_low=round(low, 3),
                expected_high=round(high, 3),
                score=round(score, 3),
                severity=severity,
                explanation="",
                detector="robust_zscore",
                confidence=confidence_from_score(score, "robust_zscore"),
            )
        )

    joint = _isolation_forest_finding(grouped)
    if joint is not None and not any(r.signal == joint.signal for r in results):
        results.append(joint)

    results.sort(key=lambda r: abs(r.score), reverse=True)
    return results


def _isolation_forest_finding(grouped: pd.DataFrame) -> AnomalyResult | None:
    """Score the newest bucket's joint feature vector with an IsolationForest.

    Args:
        grouped: Per-bucket features for one API, ascending by bucket.

    Returns:
        AnomalyResult | None: A ``multivariate`` detection when the newest
        bucket is an outlier in the joint space, otherwise ``None``.
    """
    features = grouped[["p95_ms", "req_count", "err_rate"]].astype("float64")
    if "saturation_pct" in grouped:
        features = features.assign(saturation_pct=grouped["saturation_pct"].astype("float64"))

    try:
        model = fit_isolation_forest(features.iloc[:-1])
    except (ValueError, RuntimeError) as exc:
        logger.debug("IsolationForest fit skipped: %s", exc)
        return None

    newest = features.iloc[[-1]].to_numpy(dtype="float64")
    if model.predict(newest)[0] != -1:  # type: ignore[attr-defined]
        return None

    # decision_function is negative for outliers; flip it so "higher is more
    # anomalous" holds across both detectors and the sort in `detect` is valid.
    score = float(-model.decision_function(newest)[0])  # type: ignore[attr-defined]
    p95 = float(features["p95_ms"].iloc[-1])
    low, high = _band(features["p95_ms"], window=30, threshold=DEFAULT_Z_THRESHOLD)
    return AnomalyResult(
        signal="multivariate",
        metric_value=round(p95, 3),
        expected_low=round(low, 3),
        expected_high=round(high, 3),
        score=round(score, 4),
        severity="warning",
        explanation="",
        detector="isolation_forest",
        confidence=confidence_from_score(score, "isolation_forest"),
    )
