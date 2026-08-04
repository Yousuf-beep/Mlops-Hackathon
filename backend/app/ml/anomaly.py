"""Anomaly detection over Golden-Signal rollups (phase 3 — signatures only).

Planned approach
----------------
Two complementary detectors, because API incidents come in two shapes:

1. **Robust z-score on a rolling baseline** (per API × endpoint × signal).
   Uses median and MAD rather than mean and standard deviation so a single
   spike does not inflate the baseline and mask the next one. Catches sudden
   univariate breaks — a latency cliff, an error burst.

2. **scikit-learn IsolationForest** over the joint feature vector
   ``(p95_ms, req_count, err_rate, saturation_pct)``. Catches *combinations*
   that are individually unremarkable but jointly abnormal — for example
   traffic collapsing while latency stays flat, which a per-signal detector
   never sees.

Every detection is written to the ``alert`` table with a natural-language
``explanation`` and the ``expected_range`` it violated, so the dashboard can
answer "why did this fire?" rather than only "something fired".
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


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
    """

    signal: str
    metric_value: float
    expected_low: float
    expected_high: float
    score: float
    severity: str
    explanation: str
    detector: str


def robust_zscore(series: pd.Series, window: int = 30, threshold: float = 3.5) -> pd.Series:
    """Score each point by its robust z-score against a trailing window.

    Uses ``0.6745 * (x - median) / MAD``, the standard MAD-based estimator.

    Args:
        series: Metric series indexed by minute bucket.
        window: Trailing baseline length in samples.
        threshold: Score above which a point counts as anomalous.

    Returns:
        pd.Series: Robust z-scores aligned with the input index.

    Raises:
        NotImplementedError: Phase 3.
    """
    raise NotImplementedError("phase 3: anomaly.robust_zscore")


def fit_isolation_forest(features: pd.DataFrame, contamination: float = 0.02) -> object:
    """Fit an IsolationForest on multivariate Golden-Signal features.

    Args:
        features: Rows of ``(p95_ms, req_count, err_rate, saturation_pct)``.
        contamination: Expected proportion of anomalous rows.

    Returns:
        object: The fitted ``sklearn.ensemble.IsolationForest``.

    Raises:
        NotImplementedError: Phase 3.
    """
    raise NotImplementedError("phase 3: anomaly.fit_isolation_forest")


def detect(rollups: pd.DataFrame, slo_latency_ms: int = 500) -> list[AnomalyResult]:
    """Run both detectors over a window of rollups and merge their findings.

    Args:
        rollups: Recent rows from ``metric_rollup`` for one API.
        slo_latency_ms: The API's latency objective, used to grade severity.

    Returns:
        list[AnomalyResult]: Detections, de-duplicated across detectors and
        ordered by descending score.

    Raises:
        NotImplementedError: Phase 3.
    """
    raise NotImplementedError("phase 3: anomaly.detect")


def explain(result: AnomalyResult, api_name: str, endpoint: str | None) -> str:
    """Render a one-sentence explanation for an anomaly.

    Args:
        result: The detection to describe.
        api_name: Human-readable API name.
        endpoint: Endpoint template, or ``None`` for API-wide.

    Returns:
        str: For example ``"p95 latency 812 ms on /orders is 4.1x the expected
        120-180 ms band for this time of day."``

    Raises:
        NotImplementedError: Phase 3.
    """
    raise NotImplementedError("phase 3: anomaly.explain")
