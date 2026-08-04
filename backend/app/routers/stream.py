"""Server-Sent Events stream that pushes live updates to the dashboard.

SSE rather than WebSockets: PulseGrid's realtime traffic is strictly
server→client, SSE is plain HTTP (so it survives proxies and needs no protocol
upgrade), and browsers reconnect automatically. WebSockets would add a second
protocol for no gain.

Phase 1 emits only a periodic ``heartbeat`` event. That is deliberate — it
proves the streaming plumbing (chunked ``text/event-stream`` response,
disconnect handling, buffering headers) end to end before phase 2 starts
pushing real metric frames onto the same channel.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["stream"])

#: Headers that stop intermediaries from buffering the stream. Without
#: ``X-Accel-Buffering: no`` an nginx ingress will hold chunks back and the
#: dashboard appears frozen.
SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def format_sse(event: str, data: dict[str, object]) -> str:
    """Render one SSE frame.

    Args:
        event: The event name the browser's ``addEventListener`` binds to.
        data: JSON-serialisable payload.

    Returns:
        str: A complete frame, terminated by the mandatory blank line.
    """
    return f"event: {event}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


async def heartbeat_generator(request: Request, limit: int | None = None) -> AsyncIterator[str]:
    """Yield a ``heartbeat`` frame on a fixed interval until the client leaves.

    Args:
        request: The inbound request, polled for client disconnection so an
            abandoned stream does not keep a worker slot alive forever.
        limit: Stop after this many events. ``None`` streams indefinitely.

    Yields:
        str: Formatted SSE frames.
    """
    seq = 0
    while limit is None or seq < limit:
        if await request.is_disconnected():
            logger.debug("SSE client disconnected after %d heartbeats", seq)
            break
        seq += 1
        yield format_sse(
            "heartbeat",
            {
                "seq": seq,
                "ts": datetime.now(UTC).isoformat(),
                "env": settings.ENV,
            },
        )
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
            "description": "An unbounded stream of `heartbeat` events.",
        }
    },
)
async def stream(
    request: Request,
    limit: Annotated[
        int | None,
        Query(ge=1, le=1000, description="Stop after N events. Omit for an unbounded stream."),
    ] = None,
) -> StreamingResponse:
    """Open a Server-Sent Events stream.

    Args:
        request: The inbound request.
        limit: Optional cap on the number of events, used by tests and demos.

    Returns:
        StreamingResponse: A ``text/event-stream`` response emitting a
        ``heartbeat`` event every ``SSE_HEARTBEAT_SECONDS`` seconds.
    """
    return StreamingResponse(
        heartbeat_generator(request, limit=limit),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
