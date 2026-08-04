"""Server-Sent Events stream that pushes live updates to the dashboard.

SSE rather than WebSockets: PulseGrid's realtime traffic is strictly
server→client, SSE is plain HTTP (so it survives proxies and needs no protocol
upgrade), and browsers reconnect automatically. WebSockets would add a second
protocol for no gain.

Frames
------
``heartbeat``
    Liveness only. Lets the dashboard show "connected" and lets intermediaries
    see traffic on an otherwise idle stream.
``snapshot``
    The fleet's current standing: the header tiles, one row per API, and the
    open alerts. This is the frame the dashboard actually renders from.

Both are emitted on the same ``SSE_HEARTBEAT_SECONDS`` cadence. The snapshot is
pushed rather than polled so that a dashboard left open on a wall display stays
current without the client having to guess a refresh interval.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlmodel import Session, col, select

from app import analytics as queries
from app.config import settings
from app.database import get_session
from app.models import Alert
from app.schemas import AnomalyRead

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["stream"])

SessionDep = Annotated[Session, Depends(get_session)]

#: Headers that stop intermediaries from buffering the stream. Without
#: ``X-Accel-Buffering: no`` an nginx ingress will hold chunks back and the
#: dashboard appears frozen.
SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}

#: Alerts carried on each snapshot frame. The full history is a paginated REST
#: call; the stream only carries what the incident panel shows at a glance.
SNAPSHOT_ALERT_LIMIT = 20


def format_sse(event: str, data: dict[str, object]) -> str:
    """Render one SSE frame.

    Args:
        event: The event name the browser's ``addEventListener`` binds to.
        data: JSON-serialisable payload.

    Returns:
        str: A complete frame, terminated by the mandatory blank line.
    """
    return f"event: {event}\ndata: {json.dumps(data, separators=(',', ':'), default=str)}\n\n"


def build_snapshot(session: Session, window_min: int) -> dict[str, object]:
    """Assemble the payload of one ``snapshot`` frame.

    Args:
        session: Active database session.
        window_min: Look-back window the tiles and rows summarise.

    Returns:
        dict[str, object]: Fleet summary, per-API rows and recent alerts.
    """
    recent_alerts = session.exec(
        select(Alert).order_by(col(Alert.fired_at).desc()).limit(SNAPSHOT_ALERT_LIMIT)
    ).all()
    return {
        "window_min": window_min,
        "generated_at": datetime.now(UTC).isoformat(),
        "summary": queries.fleet_summary(session, window_min).model_dump(),
        "apis": [item.model_dump() for item in queries.api_overview(session, window_min)],
        "alerts": [
            AnomalyRead.model_validate(alert).model_dump(mode="json") for alert in recent_alerts
        ],
    }


async def event_generator(
    request: Request,
    session: Session,
    window_min: int,
    limit: int | None = None,
) -> AsyncIterator[str]:
    """Yield ``heartbeat`` + ``snapshot`` frames until the client leaves.

    Args:
        request: The inbound request, polled for client disconnection so an
            abandoned stream does not keep a worker slot alive forever.
        session: Active database session, reused across ticks.
        window_min: Look-back window for each snapshot.
        limit: Stop after this many ticks. ``None`` streams indefinitely.

    Yields:
        str: Formatted SSE frames, two per tick.
    """
    seq = 0
    while limit is None or seq < limit:
        if await request.is_disconnected():
            logger.debug("SSE client disconnected after %d tick(s)", seq)
            break
        seq += 1

        yield format_sse(
            "heartbeat",
            {"seq": seq, "ts": datetime.now(UTC).isoformat(), "env": settings.ENV},
        )

        try:
            # End the previous transaction first. A session that holds one open
            # keeps serving the snapshot it already read, so the dashboard would
            # sit on stale numbers no matter how often we push.
            session.rollback()
            payload = build_snapshot(session, window_min)
            payload["seq"] = seq
            yield format_sse("snapshot", payload)
        except Exception:
            # A broken snapshot must not kill the stream; the client would
            # reconnect into the same failure and spin.
            logger.exception("failed to build SSE snapshot")

        if limit is not None and seq >= limit:
            break
        await asyncio.sleep(settings.SSE_HEARTBEAT_SECONDS)


@router.get(
    "/stream",
    summary="Live dashboard event stream (SSE)",
    response_class=StreamingResponse,
    responses={
        200: {
            "content": {"text/event-stream": {}},
            "description": "A stream of `heartbeat` and `snapshot` events.",
        }
    },
)
async def stream(
    request: Request,
    session: SessionDep,
    window_min: Annotated[
        int, Query(ge=1, le=1440, description="Look-back window each snapshot covers.")
    ] = 60,
    limit: Annotated[
        int | None,
        Query(ge=1, le=1000, description="Stop after N ticks. Omit for an unbounded stream."),
    ] = None,
) -> StreamingResponse:
    """Open a Server-Sent Events stream.

    Args:
        request: The inbound request.
        session: Active database session, held for the life of the stream.
        window_min: Look-back window each snapshot summarises.
        limit: Optional cap on the number of ticks, used by tests and demos.

    Returns:
        StreamingResponse: A ``text/event-stream`` response emitting a
        ``heartbeat`` and a ``snapshot`` every ``SSE_HEARTBEAT_SECONDS``.
    """
    return StreamingResponse(
        event_generator(request, session, window_min, limit=limit),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
