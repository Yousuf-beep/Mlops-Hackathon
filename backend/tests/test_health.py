"""Tests for the ``/health`` probe and the generated OpenAPI document."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_reports_ok_when_database_is_reachable(client: TestClient) -> None:
    """``/health`` returns ``ok``/``up`` when the database answers a ping."""
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["db"] == "up"
    assert body["version"]


def test_openapi_document_lists_every_router(client: TestClient) -> None:
    """Every phase-1 route group is present in the OpenAPI document."""
    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    for expected in (
        "/health",
        "/v1/auth/register",
        "/v1/auth/login",
        "/v1/apis",
        "/v1/ingest",
        "/proxy/{path}",
        "/v1/analytics/latency",
        "/v1/analytics/summary",
        "/v1/forecast/{api_id}",
        "/v1/anomalies/{api_id}",
        "/v1/models/metrics",
        "/v1/stream",
        "/v1/infra/snapshot",
        "/v1/infra/containers",
        "/v1/infra/environments",
    ):
        assert expected in paths, f"{expected} missing from the OpenAPI document"


def test_docs_ui_is_served(client: TestClient) -> None:
    """The Swagger UI page is reachable at ``/docs``."""
    response = client.get("/docs")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
