"""First-boot provisioning so a fresh stack is immediately alive.

A monitoring platform with an empty registry looks broken: no APIs, no traffic,
no charts, and no way to tell "correctly deployed" from "silently failing". On
first boot PulseGrid therefore creates one operator account and registers the
three bundled demo endpoints, which the prober starts exercising within
seconds.

This is strictly a convenience for local and demo runs. It is idempotent (it
does nothing once a registry row exists) and switched off with
``DEMO_AUTOSEED=false`` — which any real deployment should do, since it also
creates a well-known password.
"""

from __future__ import annotations

import logging

from sqlmodel import Session, select

from app.auth.security import hash_password
from app.config import settings
from app.models import ApiRegistry, User, UserRole

logger = logging.getLogger(__name__)

#: (name, proxy slug, upstream path, latency SLO in ms) for each demo endpoint.
#: The SLOs are set just tight enough that ``/slow`` and ``/flaky`` genuinely
#: breach them — a demo where everything is green demonstrates nothing.
#: Names stay ASCII on purpose: they travel through the database, JSON and a
#: terminal, and a decorative separator is the kind of character that survives
#: none of those reliably.
DEMO_APIS: tuple[tuple[str, str, str, int], ...] = (
    ("Demo fast", "demo-fast", "/fast", 250),
    ("Demo slow", "demo-slow", "/slow", 400),
    ("Demo flaky", "demo-flaky", "/flaky", 250),
)


def ensure_admin(session: Session) -> User:
    """Return the demo operator account, creating it if absent.

    Args:
        session: Active database session.

    Returns:
        User: The administrator that owns the seeded APIs.
    """
    existing = session.exec(select(User).where(User.email == settings.DEMO_ADMIN_EMAIL)).first()
    if existing is not None:
        return existing

    user = User(
        email=settings.DEMO_ADMIN_EMAIL,
        hashed_password=hash_password(settings.DEMO_ADMIN_PASSWORD),
        role=UserRole.ADMIN,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    logger.info("seeded operator account %s", user.email)
    return user


def seed_demo_apis(session: Session) -> int:
    """Register the bundled demo endpoints if the registry is empty.

    Args:
        session: Active database session.

    Returns:
        int: Number of APIs registered; ``0`` when the registry already had
        rows, so a user's own registrations are never joined by demo noise.
    """
    if session.exec(select(ApiRegistry)).first() is not None:
        return 0

    owner = ensure_admin(session)
    base = settings.DEMO_TARGET_URL.rstrip("/")
    for name, slug, path, slo_latency_ms in DEMO_APIS:
        session.add(
            ApiRegistry(
                name=name,
                base_url=f"/{slug}",
                upstream_url=f"{base}{path}",
                owner_user_id=owner.id or 0,
                auth_type="none",
                slo_target=0.99,
                slo_latency_ms=slo_latency_ms,
            )
        )
    session.commit()
    logger.info("seeded %d demo api(s) against %s", len(DEMO_APIS), base)
    return len(DEMO_APIS)


def bootstrap(session: Session) -> None:
    """Run first-boot provisioning, honouring ``DEMO_AUTOSEED``.

    Failures are logged, not raised: a seeding problem must never stop the API
    from starting, because the API is still perfectly usable without demo data.

    Args:
        session: Active database session.
    """
    if not settings.DEMO_AUTOSEED:
        logger.info("demo autoseed disabled")
        return
    try:
        seed_demo_apis(session)
    except Exception:
        logger.exception("demo autoseed failed; continuing without it")
