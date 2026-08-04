"""Tests for the ``/v1/apis`` registry CRUD routes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import TEST_PASSWORD

NEW_API = {
    "name": "Demo Target",
    "base_url": "/proxy/demo",
    "upstream_url": "http://demo-target:8001",
    "auth_type": "none",
    "slo_target": 0.995,
    "slo_latency_ms": 300,
}


def _create_api(client: TestClient, headers: dict[str, str], **overrides: object) -> dict:
    """Create an API and return its serialised body.

    Args:
        client: HTTP client.
        headers: Authorization header of the owner.
        **overrides: Fields to override on :data:`NEW_API`.

    Returns:
        dict: The created registry row.
    """
    response = client.post("/v1/apis", json={**NEW_API, **overrides}, headers=headers)
    assert response.status_code == 201, response.text
    return dict(response.json())


def test_crud_happy_path(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Create, read, list, update and delete a registry entry."""
    created = _create_api(client, auth_headers)
    api_id = created["id"]
    assert created["name"] == NEW_API["name"]
    assert created["slo_latency_ms"] == 300

    fetched = client.get(f"/v1/apis/{api_id}", headers=auth_headers)
    assert fetched.status_code == 200
    assert fetched.json() == created

    listed = client.get("/v1/apis", headers=auth_headers)
    assert listed.status_code == 200
    assert [row["id"] for row in listed.json()] == [api_id]

    updated = client.patch(
        f"/v1/apis/{api_id}",
        json={"name": "Renamed", "slo_latency_ms": 250},
        headers=auth_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Renamed"
    assert updated.json()["slo_latency_ms"] == 250
    assert updated.json()["upstream_url"] == NEW_API["upstream_url"], "unset fields must survive"

    deleted = client.delete(f"/v1/apis/{api_id}", headers=auth_headers)
    assert deleted.status_code == 204

    assert client.get(f"/v1/apis/{api_id}", headers=auth_headers).status_code == 404


def test_defaults_are_applied(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Omitted SLO fields fall back to the documented defaults."""
    response = client.post(
        "/v1/apis",
        json={"name": "Minimal", "base_url": "/proxy/min", "upstream_url": "http://x:8001"},
        headers=auth_headers,
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["slo_target"] == 0.99
    assert body["slo_latency_ms"] == 500
    assert body["auth_type"] is None


def test_unknown_id_returns_404(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Reading a non-existent API returns the standard 404 shape."""
    response = client.get("/v1/apis/999999", headers=auth_headers)

    assert response.status_code == 404
    assert response.json()["detail"] == "api not found"


def test_routes_require_authentication(client: TestClient) -> None:
    """Every registry route rejects unauthenticated callers with 401."""
    assert client.get("/v1/apis").status_code == 401
    assert client.post("/v1/apis", json=NEW_API).status_code == 401
    assert client.get("/v1/apis/1").status_code == 401
    assert client.patch("/v1/apis/1", json={"name": "x"}).status_code == 401
    assert client.delete("/v1/apis/1").status_code == 401


def test_apis_are_scoped_to_their_owner(client: TestClient, auth_headers: dict[str, str]) -> None:
    """A second viewer can neither list nor read another viewer's API."""
    created = _create_api(client, auth_headers)

    client.post(
        "/v1/auth/register",
        json={"email": "other@pulsegrid.dev", "password": TEST_PASSWORD},
    )
    other_login = client.post(
        "/v1/auth/login",
        json={"email": "other@pulsegrid.dev", "password": TEST_PASSWORD},
    )
    other_headers = {"Authorization": f"Bearer {other_login.json()['access_token']}"}

    assert client.get("/v1/apis", headers=other_headers).json() == []
    assert client.get(f"/v1/apis/{created['id']}", headers=other_headers).status_code == 404


def test_admin_sees_every_api(client: TestClient, auth_headers: dict[str, str]) -> None:
    """An administrator lists APIs owned by other accounts."""
    _create_api(client, auth_headers)

    client.post(
        "/v1/auth/register",
        json={"email": "boss@pulsegrid.dev", "password": TEST_PASSWORD, "role": "admin"},
    )
    admin_login = client.post(
        "/v1/auth/login",
        json={"email": "boss@pulsegrid.dev", "password": TEST_PASSWORD},
    )
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}

    listed = client.get("/v1/apis", headers=admin_headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1


def test_validation_rejects_an_impossible_slo(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """An availability target above 1.0 is rejected by schema validation."""
    response = client.post(
        "/v1/apis",
        json={**NEW_API, "slo_target": 1.5},
        headers=auth_headers,
    )

    assert response.status_code == 422
