"""Contract tests for the phase-1 stubs and the SSE heartbeat stream.

These lock in two things the later phases must not break: every unimplemented
route answers with the agreed ``501 {"detail": "not implemented: <name>"}``
shape, and the streaming plumbing genuinely produces ``text/event-stream``
frames.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

STUB_ROUTES: list[tuple[str, str, str]] = [
    ("GET", "/v1/analytics/latency?api_id=1", "analytics.latency"),
    ("GET", "/v1/analytics/traffic?api_id=1", "analytics.traffic"),
    ("GET", "/v1/analytics/errors?api_id=1", "analytics.errors"),
    ("GET", "/v1/analytics/health?api_id=1", "analytics.health"),
    ("GET", "/v1/analytics/summary", "analytics.summary"),
    ("GET", "/v1/forecast/1", "ml.forecast"),
    ("GET", "/v1/anomalies/1", "ml.anomalies"),
    ("GET", "/v1/models/metrics", "ml.model_metrics"),
    ("GET", "/proxy/anything/nested", "proxy.forward"),
]


@pytest.mark.parametrize(("method", "path", "name"), STUB_ROUTES, ids=[r[2] for r in STUB_ROUTES])
def test_stub_routes_return_the_standard_501(
    client: TestClient, method: str, path: str, name: str
) -> None:
    """Each stub returns 501 with the agreed ``not implemented: <name>`` detail."""
    response = client.request(method, path)

    assert response.status_code == 501, response.text
    assert response.json() == {"detail": f"not implemented: {name}"}


def test_ingest_stub_returns_501(client: TestClient) -> None:
    """``POST /v1/ingest`` validates its body, then reports 501."""
    response = client.post(
        "/v1/ingest",
        json=[
            {
                "api_id": 1,
                "endpoint": "/fast",
                "method": "GET",
                "status_code": 200,
                "latency_ms": 12.5,
            }
        ],
    )

    assert response.status_code == 501
    assert response.json() == {"detail": "not implemented: ingest.batch"}


def test_stream_emits_sse_heartbeats(client: TestClient) -> None:
    """``/v1/stream`` returns bounded ``heartbeat`` frames in SSE wire format."""
    with client.stream("GET", "/v1/stream?limit=2") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert response.headers["x-accel-buffering"] == "no"
        body = "".join(response.iter_text())

    assert body.count("event: heartbeat") == 2
    assert body.count("data: ") == 2
    assert body.endswith("\n\n")
    assert '"seq":1' in body
    assert '"seq":2' in body
