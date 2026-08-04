"""Database engine, session factory and FastAPI session dependency.

A single module-level :class:`~sqlalchemy.engine.Engine` is shared by the whole
process. ``pool_pre_ping`` is enabled so that connections recycled by
PostgreSQL (or by a container restart) are transparently replaced instead of
raising ``OperationalError`` on the first query after an idle period.
"""

from collections.abc import Iterator

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, SQLModel, create_engine

from app.config import settings


def _engine_options(database_url: str) -> dict[str, object]:
    """Pick engine options appropriate for the target dialect.

    SQLite (used by the test suite) has no connection pool to size, and passing
    ``pool_size``/``max_overflow`` to it is a ``TypeError``.

    Args:
        database_url: The SQLAlchemy URL the engine will be built from.

    Returns:
        dict[str, object]: Keyword arguments for ``create_engine``.
    """
    options: dict[str, object] = {"pool_pre_ping": True, "echo": False, "future": True}
    if not database_url.startswith("sqlite"):
        options |= {"pool_size": 10, "max_overflow": 20}
    return options


engine: Engine = create_engine(settings.DATABASE_URL, **_engine_options(settings.DATABASE_URL))  # type: ignore[arg-type]


def get_session() -> Iterator[Session]:
    """Yield a request-scoped database session.

    Used as a FastAPI dependency (``Depends(get_session)``). The session is
    closed when the request finishes, returning its connection to the pool.

    Yields:
        Session: An open SQLModel session bound to the shared engine.
    """
    with Session(engine) as session:
        yield session


def check_connection(session: Session) -> bool:
    """Ping the database with a trivial query.

    Args:
        session: The session to probe. Passing the session in (rather than
            using the module-level engine) keeps ``/health`` honest under test,
            where the session dependency is overridden.

    Returns:
        bool: ``True`` if the database answered, ``False`` otherwise.
    """
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return False
    return True


def create_db_and_tables() -> None:
    """Create every table declared on ``SQLModel.metadata``.

    Only used for local throwaway databases and tests. Production schema
    changes always go through Alembic migrations so that indexes created with
    raw SQL (for example the BRIN index on ``request_log.time``) are applied.
    """
    import app.models  # noqa: F401  # ensure every table is registered

    SQLModel.metadata.create_all(engine)
