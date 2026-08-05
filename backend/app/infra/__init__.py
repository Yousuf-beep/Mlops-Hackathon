"""Runtime infrastructure discovery.

PulseGrid monitors APIs, and the containers those APIs run in are part of the
picture an operator needs during triage. This package reads the *live* Docker
Engine rather than any checked-in manifest, so what the dashboard shows is what
is actually running: which services exist, which ports they publish, and which
localhost URLs those ports resolve to.

Nothing here is required for the rest of the application to work. When the
Docker socket is not reachable — the API running outside a container, a
Kubernetes deployment with no socket mounted, a hardened host — discovery
degrades to an empty result carrying the reason, and the dashboard says so
instead of showing a broken panel.
"""

from app.infra.discovery import discover, reset_cache
from app.infra.engine import close_engine

__all__ = ["close_engine", "discover", "reset_cache"]
