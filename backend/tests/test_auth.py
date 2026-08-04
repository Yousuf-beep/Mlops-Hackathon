"""Tests for registration, login and token-guarded access."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.auth.security import (
    TokenError,
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)
from tests.conftest import TEST_EMAIL, TEST_PASSWORD


def test_register_creates_a_user_and_hides_the_password(client: TestClient) -> None:
    """Registration returns 201 and never echoes the password or its digest."""
    response = client.post(
        "/v1/auth/register",
        json={"email": "new@pulsegrid.dev", "password": "a-good-password"},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["email"] == "new@pulsegrid.dev"
    assert body["role"] == "viewer"
    assert "password" not in body
    assert "hashed_password" not in body


def test_register_rejects_a_duplicate_email(client: TestClient, registered_user: dict) -> None:
    """A second registration with the same email returns 409."""
    response = client.post(
        "/v1/auth/register",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "email already registered"


def test_register_rejects_a_short_password(client: TestClient) -> None:
    """Passwords shorter than the 8-character minimum are rejected by validation."""
    response = client.post(
        "/v1/auth/register",
        json={"email": "short@pulsegrid.dev", "password": "tiny"},
    )

    assert response.status_code == 422


def test_login_returns_a_usable_token(client: TestClient, registered_user: dict) -> None:
    """Correct credentials yield a bearer token that identifies the caller."""
    response = client.post(
        "/v1/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0

    me = client.get("/v1/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["email"] == TEST_EMAIL


def test_login_rejects_a_wrong_password(client: TestClient, registered_user: dict) -> None:
    """A wrong password returns 401 with the generic message."""
    response = client.post(
        "/v1/auth/login",
        json={"email": TEST_EMAIL, "password": "definitely-wrong"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "invalid email or password"


def test_login_rejects_an_unknown_email_identically(client: TestClient) -> None:
    """An unknown account returns the same 401 body, so accounts cannot be enumerated."""
    response = client.post(
        "/v1/auth/login",
        json={"email": "ghost@pulsegrid.dev", "password": TEST_PASSWORD},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "invalid email or password"


@pytest.mark.parametrize(
    "headers",
    [
        pytest.param({}, id="no-header"),
        pytest.param({"Authorization": "Bearer not-a-jwt"}, id="malformed-token"),
        pytest.param({"Authorization": "Basic abc123"}, id="wrong-scheme"),
    ],
)
def test_me_requires_a_valid_bearer_token(client: TestClient, headers: dict) -> None:
    """``/v1/auth/me`` rejects missing, malformed and wrong-scheme credentials."""
    response = client.get("/v1/auth/me", headers=headers)

    assert response.status_code == 401


# --------------------------------------------------------------------------- #
# Unit tests for the pure security helpers                                     #
# --------------------------------------------------------------------------- #


def test_password_hashing_round_trip() -> None:
    """A digest verifies against its own plaintext and nothing else."""
    digest = hash_password("correct horse battery")

    assert digest != "correct horse battery"
    assert verify_password("correct horse battery", digest)
    assert not verify_password("wrong horse battery", digest)


def test_verify_password_tolerates_a_corrupt_digest() -> None:
    """A malformed digest returns ``False`` instead of raising."""
    assert not verify_password("anything", "not-a-bcrypt-digest")


def test_hash_password_rejects_oversized_input() -> None:
    """Input beyond bcrypt's 72-byte limit is rejected rather than truncated."""
    with pytest.raises(ValueError, match="72 bytes"):
        hash_password("x" * 73)


def test_token_round_trip_carries_subject_and_role() -> None:
    """A freshly issued token decodes back to its claims."""
    token, expires_in = create_access_token(subject=42, role="admin")
    claims = decode_token(token)

    assert claims["sub"] == "42"
    assert claims["role"] == "admin"
    assert expires_in > 0


def test_decode_token_rejects_a_tampered_token() -> None:
    """A token whose signature does not match raises :class:`TokenError`."""
    token, _ = create_access_token(subject=1, role="viewer")

    with pytest.raises(TokenError):
        decode_token(token + "tampered")
