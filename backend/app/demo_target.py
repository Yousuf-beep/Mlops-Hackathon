"""A tiny, deliberately imperfect upstream API for PulseGrid to monitor.

Run with ``uvicorn app.demo_target:app --port 8001`` (the ``demo-target``
compose service does exactly this). It ships with the backend image rather than
as a separate service so there is only one image to build and push.

It exists so the platform has something real to proxy, probe and chart from day
one — ``/slow`` produces a latency distribution worth computing percentiles
over, and ``/flaky`` produces a non-zero error rate for the error signal and
the anomaly detector.
"""

from __future__ import annotations

import asyncio
import random
from typing import Literal

from fastapi import FastAPI, Response, status
from pydantic import BaseModel

app = FastAPI(
    title="PulseGrid Demo Target",
    description="A synthetic upstream with fast, slow and flaky endpoints.",
    version="0.1.0",
)

#: Latency band for ``/slow``, in milliseconds.
SLOW_MIN_MS = 100
SLOW_MAX_MS = 800

#: Probability that ``/flaky`` fails with a 500.
FLAKY_ERROR_RATE = 0.10


class EchoResponse(BaseModel):
    """Standard demo-target reply."""

    endpoint: Literal["fast", "slow", "flaky", "health"]
    latency_ms: float
    message: str


@app.get("/health", response_model=EchoResponse, summary="Demo-target liveness probe")
async def health() -> EchoResponse:
    """Return immediately so compose can health-check the service.

    Returns:
        EchoResponse: A constant healthy reply.
    """
    return EchoResponse(endpoint="health", latency_ms=0.0, message="demo-target is up")


@app.get("/fast", response_model=EchoResponse, summary="Always fast, always 200")
async def fast() -> EchoResponse:
    """Respond instantly.

    Returns:
        EchoResponse: A zero-latency reply.
    """
    return EchoResponse(endpoint="fast", latency_ms=0.0, message="instant")


@app.get("/slow", response_model=EchoResponse, summary="Random 100-800 ms latency")
async def slow() -> EchoResponse:
    """Sleep for a random interval before replying.

    Returns:
        EchoResponse: The reply, annotated with the latency actually slept.
    """
    delay_ms = random.uniform(SLOW_MIN_MS, SLOW_MAX_MS)  # noqa: S311 - synthetic load, not crypto
    await asyncio.sleep(delay_ms / 1000.0)
    return EchoResponse(endpoint="slow", latency_ms=round(delay_ms, 2), message="slept")


@app.get("/flaky", response_model=EchoResponse, summary="Fails with a 500 ~10% of the time")
async def flaky(response: Response) -> EchoResponse:
    """Fail with a 500 roughly one call in ten.

    Args:
        response: Injected so the status code can be set without raising, which
            keeps the response body shape identical on success and failure.

    Returns:
        EchoResponse: The reply; the HTTP status is 500 on the failure path.
    """
    if random.random() < FLAKY_ERROR_RATE:  # noqa: S311 - synthetic load, not crypto
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return EchoResponse(endpoint="flaky", latency_ms=0.0, message="synthetic upstream failure")
    return EchoResponse(endpoint="flaky", latency_ms=0.0, message="ok")
