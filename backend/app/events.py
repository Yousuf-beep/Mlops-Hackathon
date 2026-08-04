"""Process-local "something changed" signal for the SSE stream.

The rollup table only settles once a minute, but a caller of `/v1/stream`
should see a new request, a new alert or a new forecast far sooner than that.
Rather than adding a message broker, this is a single monotonically
increasing counter: any writer bumps it, and `app/routers/stream.py` short-polls
it instead of sleeping a fixed interval, rebuilding a snapshot only when the
counter has actually moved.

Modeled on the lock-guarded module-level store in `app/ml/metrics_store.py` —
the same thread-safety need applies here: APScheduler jobs (rollup, anomaly,
forecast) and the active prober write from worker threads, the reverse proxy
and ingest endpoint write from the event loop's request handlers, and the SSE
generator reads from the event loop. A plain `threading.Lock` around an int is
enough; there is no ordering or delivery guarantee to make beyond "at least one
rebuild happens after the last write".
"""

from __future__ import annotations

import threading

_LOCK = threading.Lock()
_VERSION = 0


def mark_dirty() -> None:
    """Signal that fresh data is available for the next snapshot.

    Called after every ``request_log`` insert (proxy, ingest, prober all funnel
    through :func:`app.routers.ingest.record_call`) and after each anomaly/
    forecast job run, so the stream reflects new alerts and forecasts without
    waiting for the next fixed tick.
    """
    global _VERSION
    with _LOCK:
        _VERSION += 1


def version() -> int:
    """Return the current dirty-counter value.

    Returns:
        int: Monotonically increasing; callers compare against a previously
        observed value to detect whether a rebuild is warranted.
    """
    with _LOCK:
        return _VERSION
