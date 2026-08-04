"""Request and response models exposed by the HTTP API.

These are plain Pydantic v2 models, kept separate from the SQLModel *table*
models in :mod:`app.models`. Keeping them separate means the wire contract can
evolve independently of the schema and, critically, that ``hashed_password``
can never leak into a response by accident.

Models for endpoints that are still stubs (analytics, ML) are declared here so
the OpenAPI document already advertises the eventual shape.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import AlertSeverity, AlertType, UserRole

# --------------------------------------------------------------------------- #
# Health                                                                       #
# --------------------------------------------------------------------------- #


class HealthResponse(BaseModel):
    """Liveness/readiness payload returned by ``GET /health``."""

    status: Literal["ok", "degraded"] = Field(description="Overall service status.")
    db: Literal["up", "down"] = Field(description="Result of a real database ping.")
    version: str = Field(description="Running application version.")


# --------------------------------------------------------------------------- #
# Auth                                                                         #
# --------------------------------------------------------------------------- #


class UserCreate(BaseModel):
    """Registration payload for ``POST /v1/auth/register``."""

    email: EmailStr = Field(description="Login identity; must be unique.")
    password: str = Field(min_length=8, max_length=72, description="Plaintext password.")
    role: UserRole = Field(default=UserRole.VIEWER, description="Requested role.")


class UserLogin(BaseModel):
    """Credentials payload for ``POST /v1/auth/login``."""

    email: EmailStr = Field(description="Registered email address.")
    password: str = Field(min_length=1, max_length=72, description="Plaintext password.")


class UserRead(BaseModel):
    """Public projection of a user. Never contains the password digest."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    role: UserRole
    created_at: datetime


class Token(BaseModel):
    """Bearer token envelope returned by ``POST /v1/auth/login``."""

    access_token: str = Field(description="Signed JWT.")
    token_type: Literal["bearer"] = Field(default="bearer", description="Auth scheme.")
    expires_in: int = Field(description="Token lifetime in seconds.")


class TokenPayload(BaseModel):
    """Decoded JWT claim set."""

    sub: str = Field(description="Subject — the user id, as a string.")
    role: UserRole = Field(description="Role snapshot at issue time.")
    exp: int = Field(description="Expiry as a POSIX timestamp.")


# --------------------------------------------------------------------------- #
# API registry                                                                 #
# --------------------------------------------------------------------------- #


class ApiCreate(BaseModel):
    """Payload for ``POST /v1/apis``."""

    name: str = Field(min_length=1, max_length=128, description="Human-readable label.")
    base_url: str = Field(min_length=1, max_length=512, description="Path served by the proxy.")
    upstream_url: str = Field(min_length=1, max_length=512, description="Real upstream origin.")
    auth_type: str | None = Field(default=None, max_length=32, description="Upstream auth hint.")
    slo_target: float = Field(default=0.99, gt=0.0, le=1.0, description="Availability objective.")
    slo_latency_ms: int = Field(default=500, gt=0, description="Latency objective in ms.")


class ApiUpdate(BaseModel):
    """Partial-update payload for ``PATCH /v1/apis/{api_id}``.

    Every field is optional; only the ones supplied are applied.
    """

    name: str | None = Field(default=None, min_length=1, max_length=128)
    base_url: str | None = Field(default=None, min_length=1, max_length=512)
    upstream_url: str | None = Field(default=None, min_length=1, max_length=512)
    auth_type: str | None = Field(default=None, max_length=32)
    slo_target: float | None = Field(default=None, gt=0.0, le=1.0)
    slo_latency_ms: int | None = Field(default=None, gt=0)


class ApiRead(BaseModel):
    """Public projection of a registered API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    base_url: str
    upstream_url: str
    owner_user_id: int
    auth_type: str | None
    slo_target: float
    slo_latency_ms: int
    created_at: datetime


# --------------------------------------------------------------------------- #
# Ingest (phase 2)                                                             #
# --------------------------------------------------------------------------- #


class IngestEvent(BaseModel):
    """A single call observation pushed by an SDK to ``POST /v1/ingest``."""

    api_id: int
    endpoint: str
    method: str
    status_code: int
    latency_ms: float
    time: datetime | None = Field(default=None, description="Defaults to server receipt time.")
    request_bytes: int | None = None
    response_bytes: int | None = None
    client_ip: str | None = None


class IngestAccepted(BaseModel):
    """Acknowledgement returned by ``POST /v1/ingest``."""

    accepted: int = Field(description="Number of events persisted.")


# --------------------------------------------------------------------------- #
# Analytics (phase 2)                                                          #
# --------------------------------------------------------------------------- #


class TimeseriesPoint(BaseModel):
    """One minute bucket of a Golden-Signal series."""

    bucket: datetime
    value: float


class TimeseriesResponse(BaseModel):
    """A named series over a time window, read from ``metric_rollup``."""

    api_id: int
    endpoint: str | None = None
    metric: str
    points: list[TimeseriesPoint] = Field(default_factory=list)


class HealthScoreResponse(BaseModel):
    """Composite health score for one API."""

    api_id: int
    score: float = Field(ge=0.0, le=100.0)
    slo_target: float
    availability: float
    p95_ms: float


class SummaryResponse(BaseModel):
    """Fleet-wide summary tiles for the dashboard header."""

    api_count: int
    total_requests: int
    error_rate: float
    p95_ms: float
    open_alerts: int


# --------------------------------------------------------------------------- #
# ML (phase 3)                                                                 #
# --------------------------------------------------------------------------- #


class ForecastPoint(BaseModel):
    """One forecast point with its prediction interval."""

    horizon_min: int
    yhat: float
    yhat_lower: float
    yhat_upper: float


class ForecastResponse(BaseModel):
    """Traffic forecast for one API."""

    api_id: int
    generated_at: datetime
    points: list[ForecastPoint] = Field(default_factory=list)


class AnomalyRead(BaseModel):
    """A detected anomaly, surfaced as an explained alert."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    api_id: int
    endpoint: str | None
    type: AlertType
    severity: AlertSeverity
    signal: str
    explanation: str
    metric_value: float
    expected_range: str
    fired_at: datetime
    resolved_at: datetime | None


class ModelMetrics(BaseModel):
    """Offline evaluation metrics for the deployed ML models."""

    model_config = ConfigDict(protected_namespaces=())

    model_name: str
    trained_at: datetime
    mae: float | None = None
    rmse: float | None = None
    mape: float | None = None
    precision: float | None = None
    recall: float | None = None


# --------------------------------------------------------------------------- #
# Errors                                                                       #
# --------------------------------------------------------------------------- #


class ErrorResponse(BaseModel):
    """The single error shape used by every PulseGrid endpoint."""

    detail: str
