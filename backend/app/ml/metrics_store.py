"""Process-local store of the latest model-evaluation metrics.

``GET /v1/models/metrics`` reports how the deployed models scored the last time
they were refit. Those numbers are derived — they can always be recomputed by
running a backtest — so they live in memory rather than in a table: persisting
them would mean a migration, a write on every refit, and a schema to keep in
step with whatever a future model reports.

The trade-off is explicit: metrics reset on restart and are per-process, so a
multi-replica deployment reports whichever replica answered. That is acceptable
for a diagnostic panel; it would not be for anything that drives a decision.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime

from app.schemas import ModelMetrics

#: Guards the store — APScheduler writes from a worker thread while request
#: handlers read from the event loop's thread pool.
_LOCK = threading.Lock()

_METRICS: dict[str, ModelMetrics] = {}


def record(model_name: str, scores: dict[str, float]) -> ModelMetrics:
    """Record the latest evaluation of one model.

    Args:
        model_name: Identifier of the model being scored.
        scores: Any subset of ``mae``, ``rmse``, ``mape``, ``precision``,
            ``recall``. Unknown keys are ignored so a detector can report extra
            diagnostics without breaking the wire contract.

    Returns:
        ModelMetrics: The stored entry.
    """
    entry = ModelMetrics(
        model_name=model_name,
        trained_at=datetime.now(UTC),
        mae=scores.get("mae"),
        rmse=scores.get("rmse"),
        mape=scores.get("mape"),
        precision=scores.get("precision"),
        recall=scores.get("recall"),
    )
    with _LOCK:
        _METRICS[model_name] = entry
    return entry


def snapshot() -> list[ModelMetrics]:
    """Return the latest metrics for every model that has reported.

    Returns:
        list[ModelMetrics]: Entries ordered by model name.
    """
    with _LOCK:
        return sorted(_METRICS.values(), key=lambda entry: entry.model_name)


def clear() -> None:
    """Drop every recorded metric. Used by tests to isolate runs."""
    with _LOCK:
        _METRICS.clear()
