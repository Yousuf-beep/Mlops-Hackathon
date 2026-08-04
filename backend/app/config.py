"""Application configuration.

All runtime configuration is read from environment variables (or a local
``.env`` file) via ``pydantic-settings``. No secret is ever hard-coded: the
defaults below are development-only placeholders and are overridden by
``docker-compose.yml`` / CI.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings loaded from the environment.

    Attributes:
        ENV: Deployment environment name (``dev``, ``test``, ``prod``).
        DATABASE_URL: SQLAlchemy URL. Must use the ``postgresql+psycopg``
            scheme so SQLAlchemy 2.x binds to the psycopg 3 driver.
        JWT_SECRET: HMAC signing key for access tokens.
        JWT_ALGORITHM: JWS algorithm used to sign access tokens.
        ACCESS_TOKEN_EXPIRE_MINUTES: Access-token lifetime in minutes.
        LOG_LEVEL: Root logging level for the application.
        SCHEDULER_ENABLED: Whether APScheduler starts with the app. Disabled
            in tests so background jobs never interfere with assertions.
        HEARTBEAT_INTERVAL_SECONDS: Period of the scheduler heartbeat job.
        SSE_HEARTBEAT_SECONDS: Period of the ``/v1/stream`` heartbeat event.
        DEMO_TARGET_URL: Base URL of the bundled demo upstream service.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    ENV: str = "dev"

    # --- database -----------------------------------------------------------
    DATABASE_URL: str = "postgresql+psycopg://pulsegrid:pulsegrid@localhost:5432/pulsegrid"

    # --- auth ---------------------------------------------------------------
    JWT_SECRET: str = "dev-only-insecure-secret-change-me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # --- runtime ------------------------------------------------------------
    LOG_LEVEL: str = "INFO"
    SCHEDULER_ENABLED: bool = True
    HEARTBEAT_INTERVAL_SECONDS: int = 60
    SSE_HEARTBEAT_SECONDS: int = 5

    # --- phase-2 upstreams --------------------------------------------------
    DEMO_TARGET_URL: str = "http://demo-target:8001"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton.

    Cached so that the ``.env`` file is parsed exactly once per process and so
    that FastAPI dependencies can depend on it without I/O cost.

    Returns:
        Settings: The validated application settings.
    """
    return Settings()


settings: Settings = get_settings()
