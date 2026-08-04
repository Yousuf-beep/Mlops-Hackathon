"""FastAPI application factory and lifespan wiring.

Run with ``uvicorn app.main:app``. The module-level :data:`app` is created by
:func:`create_app` so tests can build isolated instances without importing a
half-configured global.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session

from app import __version__
from app.bootstrap import bootstrap
from app.config import settings
from app.database import check_connection, engine, get_session
from app.jobs.scheduler import shutdown_scheduler, start_scheduler
from app.routers import analytics, auth, ingest, ml, registry, stream
from app.schemas import HealthResponse

logging.basicConfig(
    level=settings.LOG_LEVEL.upper(),
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

DESCRIPTION = """
**PulseGrid** monitors real, live APIs through a transparent reverse proxy and
turns their traffic into Golden-Signal analytics, ML-detected anomalies and
traffic forecasts.

Collection runs through `/proxy/{slug}/...` (transparent reverse proxy),
`POST /v1/ingest` (SDK push) and an active prober. Everything the dashboard
reads comes from the pre-aggregated `metric_rollup` table, and `/v1/stream`
pushes the same numbers live over Server-Sent Events.
"""


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage startup and shutdown of process-wide resources.

    Provisions demo data (when enabled), starts APScheduler on the way up and
    stops it cleanly on the way down so a container restart never leaves a job
    mid-flight.

    Args:
        app: The application being started.

    Yields:
        None: Control returns to the server for the lifetime of the app.
    """
    logger.info("PulseGrid %s starting (env=%s)", __version__, settings.ENV)
    with Session(engine) as session:
        bootstrap(session)
    start_scheduler()
    try:
        yield
    finally:
        shutdown_scheduler()
        logger.info("PulseGrid stopped")


def create_app() -> FastAPI:
    """Build and configure the FastAPI application.

    Returns:
        FastAPI: The fully wired application, with every router mounted.
    """
    app = FastAPI(
        title="PulseGrid API",
        description=DESCRIPTION,
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # The React dashboard is served from a different origin in development.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get(
        "/health",
        response_model=HealthResponse,
        tags=["meta"],
        summary="Liveness and database readiness probe",
    )
    def health(session: Annotated[Session, Depends(get_session)]) -> HealthResponse:
        """Report service and database health.

        Performs a real ``SELECT 1`` rather than reporting a cached flag, so a
        green ``/health`` genuinely means the API can serve queries.

        Args:
            session: Active database session.

        Returns:
            HealthResponse: ``status`` is ``ok`` only when the database
            answered; otherwise ``degraded`` with ``db: down``.
        """
        db_up = check_connection(session)
        return HealthResponse(
            status="ok" if db_up else "degraded",
            db="up" if db_up else "down",
            version=__version__,
        )

    app.include_router(auth.router)
    app.include_router(registry.router)
    app.include_router(ingest.router)
    app.include_router(ingest.proxy_router)
    app.include_router(analytics.router)
    app.include_router(ml.router)
    app.include_router(stream.router)

    return app


app = create_app()
