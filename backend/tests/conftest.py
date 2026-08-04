"""Shared pytest fixtures.

Tests run against **SQLite in-memory**, not PostgreSQL. The rationale:

* Phase-1 logic (auth, registry CRUD, routing, SSE plumbing) is pure SQL that
  behaves identically on both engines, so a container buys nothing.
* CI stays fast and dependency-free — no service container, no wait-for-healthy.
* The one genuinely PostgreSQL-specific artefact, the BRIN index, lives in the
  Alembic migration and is verified against real PostgreSQL in the
  ``docker compose`` acceptance run documented in the README.

When phase 2 adds ``date_trunc`` rollup queries, those tests get a PostgreSQL
service container; the split is deliberate, not accidental.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

os.environ.setdefault("ENV", "test")
os.environ.setdefault("SCHEDULER_ENABLED", "false")
os.environ.setdefault("JWT_SECRET", "test-only-secret")
os.environ.setdefault("DATABASE_URL", "sqlite://")
# Collapse the SSE pause so the stream contract test runs in milliseconds; the
# real 5-second cadence is exercised by the `curl -N` acceptance step.
os.environ.setdefault("SSE_HEARTBEAT_SECONDS", "0")

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine  # noqa: E402

from app.database import get_session  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import User  # noqa: E402  # registers every table on the metadata

TEST_EMAIL = "operator@pulsegrid.dev"
TEST_PASSWORD = "sup3r-secret-pw"


@pytest.fixture(name="session")
def session_fixture() -> Iterator[Session]:
    """Provide a fresh in-memory database for a single test.

    ``StaticPool`` keeps every connection pointed at the same in-memory
    database; without it each connection would get its own empty one.

    Yields:
        Session: A session bound to a freshly created schema.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    SQLModel.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(name="app")
def app_fixture(session: Session) -> Iterator[FastAPI]:
    """Build an app whose session dependency is bound to the test database.

    Args:
        session: The per-test session fixture.

    Yields:
        FastAPI: The application with ``get_session`` overridden.
    """
    application = create_app()
    application.dependency_overrides[get_session] = lambda: session
    yield application
    application.dependency_overrides.clear()


@pytest.fixture(name="client")
def client_fixture(app: FastAPI) -> Iterator[TestClient]:
    """Provide an unauthenticated HTTP client.

    The client is *not* used as a context manager, so the app lifespan (and
    therefore APScheduler) never starts during tests.

    Args:
        app: The test application.

    Yields:
        TestClient: A client bound to the test app.
    """
    yield TestClient(app)


@pytest.fixture(name="registered_user")
def registered_user_fixture(client: TestClient) -> dict[str, object]:
    """Register a default viewer account.

    Args:
        client: Unauthenticated HTTP client.

    Returns:
        dict[str, object]: The created user's public projection.
    """
    response = client.post(
        "/v1/auth/register",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


@pytest.fixture(name="auth_headers")
def auth_headers_fixture(client: TestClient, registered_user: dict[str, object]) -> dict[str, str]:
    """Log the default account in and return its ``Authorization`` header.

    Args:
        client: Unauthenticated HTTP client.
        registered_user: Ensures the account exists first.

    Returns:
        dict[str, str]: A ready-to-use bearer header.
    """
    response = client.post(
        "/v1/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture(name="admin_user")
def admin_user_fixture(client: TestClient, session: Session) -> User:
    """Register an administrator account and return its row.

    Args:
        client: Unauthenticated HTTP client.
        session: The test session.

    Returns:
        User: The persisted administrator.
    """
    response = client.post(
        "/v1/auth/register",
        json={"email": "admin@pulsegrid.dev", "password": TEST_PASSWORD, "role": "admin"},
    )
    assert response.status_code == 201, response.text
    user = session.get(User, response.json()["id"])
    assert user is not None
    return user
