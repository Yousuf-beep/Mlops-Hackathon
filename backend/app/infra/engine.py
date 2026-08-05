"""A minimal async client for the Docker Engine HTTP API.

The Engine speaks plain HTTP over a Unix socket (or a TCP port), which ``httpx``
— already a dependency for the reverse proxy — can talk to directly via its
``uds`` transport. That is the whole reason there is no Docker SDK in
``pyproject.toml``: the two endpoints this feature needs are ``GET
/containers/json`` and ``GET /containers/{id}/json``, and a client for those is
smaller than the dependency would be.

Paths are sent unversioned. The daemon resolves an unversioned request against
its own current API version, so this keeps working across Docker Desktop
upgrades without a pinned ``/v1.43`` prefix that eventually falls out of range.
"""

from __future__ import annotations

import asyncio
import logging
import socket
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

#: Base URL used for Unix-socket connections. The host is a placeholder — the
#: transport ignores it and dials the socket — but httpx still requires one.
_UDS_BASE_URL = "http://docker"


class DockerUnavailable(RuntimeError):
    """The Docker Engine could not be reached.

    Carries a human-readable reason so the dashboard can explain *why* the
    containers panel is empty rather than just showing nothing.
    """


def _build_client() -> httpx.AsyncClient:
    """Construct a client bound to the configured Docker endpoint.

    Understands the same ``DOCKER_HOST`` forms the Docker CLI does:
    ``unix:///var/run/docker.sock``, ``tcp://host:2375`` and explicit
    ``http(s)://`` URLs. A bare filesystem path is treated as a socket, which is
    what ``DOCKER_SOCKET=/var/run/docker.sock`` yields.

    Returns:
        httpx.AsyncClient: A client whose relative paths resolve to the Engine.

    Raises:
        DockerUnavailable: If the endpoint uses a scheme this client cannot
            speak — notably Windows named pipes, which have no httpx transport.
    """
    endpoint = settings.DOCKER_HOST.strip()
    timeout = httpx.Timeout(settings.INFRA_ENGINE_TIMEOUT_SECONDS)

    if endpoint.startswith("npipe://"):
        raise DockerUnavailable(
            "Windows named pipes are not supported; run the API in a container "
            "with /var/run/docker.sock mounted, or set DOCKER_HOST to a tcp:// endpoint"
        )

    if endpoint.startswith("unix://"):
        return httpx.AsyncClient(
            transport=httpx.AsyncHTTPTransport(uds=urlparse(endpoint).path),
            base_url=_UDS_BASE_URL,
            timeout=timeout,
        )

    if endpoint.startswith("tcp://"):
        return httpx.AsyncClient(base_url=endpoint.replace("tcp://", "http://", 1), timeout=timeout)

    if endpoint.startswith(("http://", "https://")):
        return httpx.AsyncClient(base_url=endpoint, timeout=timeout)

    # A bare path: the common case of pointing straight at a mounted socket.
    return httpx.AsyncClient(
        transport=httpx.AsyncHTTPTransport(uds=endpoint),
        base_url=_UDS_BASE_URL,
        timeout=timeout,
    )


class DockerEngine:
    """Lazily-connected handle on the Docker Engine API.

    One client is shared process-wide: the socket connection is cheap to keep
    and expensive to re-establish per request, and the discovery endpoint is
    polled by every open dashboard.
    """

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._lock = asyncio.Lock()

    async def _get_client(self) -> httpx.AsyncClient:
        """Return the shared client, building it on first use."""
        if self._client is None:
            async with self._lock:
                if self._client is None:
                    self._client = _build_client()
        return self._client

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Issue a GET against the Engine and return the decoded JSON body.

        Args:
            path: Unversioned Engine path, e.g. ``/containers/json``.
            params: Optional query parameters.

        Returns:
            Any: The decoded response body.

        Raises:
            DockerUnavailable: On any transport failure or non-2xx response.
                Every failure mode collapses to this one type because the
                caller's only reasonable response to all of them is the same:
                report that discovery is unavailable, and say why.
        """
        client = await self._get_client()
        try:
            response = await client.get(path, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            raise DockerUnavailable(
                f"Docker Engine responded {exc.response.status_code} to {path}"
            ) from exc
        except httpx.HTTPError as exc:
            raise DockerUnavailable(f"cannot reach the Docker Engine ({exc})") from exc

    async def list_containers(self, *, include_stopped: bool = True) -> list[dict[str, Any]]:
        """List containers known to the daemon.

        Args:
            include_stopped: Include containers that are not running. Stopped
                services are worth showing — "exited" is an answer, an absent
                row is not.

        Returns:
            list[dict[str, Any]]: Raw Engine container summaries.
        """
        body = await self._get("/containers/json", {"all": "1" if include_stopped else "0"})
        return body if isinstance(body, list) else []

    async def inspect(self, container_id: str) -> dict[str, Any]:
        """Fetch the full inspect payload for one container.

        The summary from :meth:`list_containers` omits health state and the
        container's own environment, both of which discovery needs.

        Args:
            container_id: Container ID or name.

        Returns:
            dict[str, Any]: The raw inspect payload.
        """
        body = await self._get(f"/containers/{container_id}/json")
        return body if isinstance(body, dict) else {}

    async def close(self) -> None:
        """Close the shared client, if one was ever opened."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None


#: Process-wide engine handle.
engine = DockerEngine()


async def close_engine() -> None:
    """Release the shared Engine client. Called from the app's lifespan."""
    await engine.close()


def self_container_id() -> str | None:
    """Best guess at the ID of the container this process is running in.

    Docker sets a container's hostname to its own short ID unless something
    overrides it, which is what lets discovery find its own compose project and
    scope the container list to sibling services — no project name to configure,
    and no other project's containers leaking into the dashboard.

    Returns:
        str | None: The short container ID, or ``None`` when the hostname does
        not look like one (the API running directly on a developer's machine,
        or a container with an explicit ``hostname:``).
    """
    name = socket.gethostname().strip()
    # Short IDs are 12 hex characters. Anything else is a real hostname, and
    # inspecting it would either 404 or — worse — match an unrelated container.
    if len(name) == 12 and all(character in "0123456789abcdef" for character in name):
        return name
    return None
