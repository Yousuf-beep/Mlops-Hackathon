"""Turn raw Docker Engine payloads into the shape the dashboard renders.

Everything in this module is derived from the live daemon. Nothing is read from
``docker-compose.yml``, and no port number of this project appears anywhere
below — a service that starts publishing a new port shows up on the next poll,
and one that stops appears as stopped rather than silently vanishing.

Three inferences are worth calling out, because they are the only places a
judgement is made rather than a value copied:

* **Scheme.** A published port is assumed to speak HTTP unless its *container*
  port is a registered port for something else (5432 is PostgreSQL wherever it
  is published). That table is the IANA registry, not this project's ports.
* **Environment.** Read from an explicit label first, then the container's own
  ``ENV``, then the compose project or container name. Anything unrecognised is
  development, because an unlabelled local container is a local container.
* **Reachability.** Probed over the container network, never over the published
  host port — a request from inside the API container to ``localhost:5173``
  would hit the API container itself, not the dashboard. See
  :func:`_probe_endpoint`.
"""

from __future__ import annotations

import asyncio
import logging
import re
import socket
from datetime import UTC, datetime
from typing import Any

import httpx

from app.config import settings
from app.infra.engine import DockerUnavailable, engine, self_container_id
from app.schemas import (
    ContainerPort,
    ContainerRead,
    EnvironmentGroup,
    InfraSnapshot,
    ServiceEndpoint,
    WebService,
)

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Inference tables                                                             #
# --------------------------------------------------------------------------- #

#: Registered ports that are *not* HTTP. Anything absent is assumed browsable,
#: which is the right default for an application container. These are IANA
#: service ports, deliberately not PulseGrid's own — nothing here changes when
#: this project's compose file does.
_WELL_KNOWN_SCHEMES: dict[int, str] = {
    22: "ssh",
    25: "smtp",
    53: "dns",
    443: "https",
    1433: "mssql",
    3306: "mysql",
    5432: "postgresql",
    5672: "amqp",
    6379: "redis",
    8443: "https",
    9092: "kafka",
    11211: "memcached",
    27017: "mongodb",
    2181: "zookeeper",
}

#: Schemes a browser can open. The rest are shown as a host:port address with
#: no link, because a dead link is worse than a plain string.
_BROWSABLE = frozenset({"http", "https"})

#: The three environments the dashboard groups web endpoints into, in the order
#: work flows through them.
ENVIRONMENTS: tuple[str, ...] = ("development", "qa", "production")

#: Display name for each environment.
_ENVIRONMENT_LABELS: dict[str, str] = {
    "development": "Development",
    "qa": "QA",
    "production": "Production",
}

#: Aliases seen in labels, env vars and names, mapped onto the three canonical
#: environments. Pre-production names (staging, uat) group with QA: they answer
#: the same question — "is the next release good?" — and a fourth column for
#: them would be three-quarters empty on every real deployment.
_ENVIRONMENT_ALIASES: dict[str, str] = {
    "dev": "development",
    "devel": "development",
    "develop": "development",
    "development": "development",
    "local": "development",
    "sandbox": "development",
    "qa": "qa",
    "test": "qa",
    "tests": "qa",
    "testing": "qa",
    "stage": "qa",
    "staging": "qa",
    "uat": "qa",
    "preprod": "qa",
    "prod": "production",
    "production": "production",
    "live": "production",
    "release": "production",
}

#: Labels consulted for an explicit environment, most specific first. The
#: Kubernetes one is not speculative — `k8s/overlays/*` already stamp it.
_ENVIRONMENT_LABEL_KEYS: tuple[str, ...] = (
    "pulsegrid.environment",
    "com.pulsegrid.environment",
    "app.kubernetes.io/environment",
    "environment",
    "env",
)

#: Host IPs that mean "every interface", and therefore that the published port
#: is reachable on whatever hostname the dashboard itself was loaded from.
_WILDCARD_HOST_IPS = frozenset({"", "0.0.0.0", "::", "[::]"})


# --------------------------------------------------------------------------- #
# Small parsers                                                                #
# --------------------------------------------------------------------------- #


def _parse_timestamp(raw: str | None) -> datetime | None:
    """Parse a Docker timestamp into an aware ``datetime``.

    The Engine emits RFC 3339 with nanosecond precision, which
    :meth:`datetime.fromisoformat` cannot read, and uses ``0001-01-01T00:00:00Z``
    as its "never" sentinel.

    Args:
        raw: The timestamp string, or ``None``.

    Returns:
        datetime | None: The parsed instant, or ``None`` when absent or never.
    """
    if not raw or raw.startswith("0001-01-01"):
        return None
    trimmed = re.sub(r"(\.\d{6})\d+", r"\1", raw.replace("Z", "+00:00"))
    try:
        return datetime.fromisoformat(trimmed)
    except ValueError:
        return None


def _normalise_environment(raw: str | None) -> str | None:
    """Map a free-form environment name onto one of :data:`ENVIRONMENTS`.

    Args:
        raw: A label value, env-var value or name fragment.

    Returns:
        str | None: The canonical environment, or ``None`` if unrecognised.
    """
    if not raw:
        return None
    return _ENVIRONMENT_ALIASES.get(raw.strip().lower())


def _environment_from_name(name: str) -> str | None:
    """Infer an environment from a project or container name.

    Matches whole segments only (``pulsegrid-qa`` but not ``pulsegrid-quality``),
    so a service whose name merely contains ``prod`` is not filed under
    production by accident.

    Args:
        name: A compose project name or container name.

    Returns:
        str | None: The canonical environment, or ``None``.
    """
    for segment in re.split(r"[-_./]", name.lower()):
        matched = _normalise_environment(segment)
        if matched:
            return matched
    return None


def _classify_environment(labels: dict[str, str], env_vars: dict[str, str], name: str) -> str:
    """Decide which environment a container belongs to.

    Precedence runs from the most deliberate signal to the weakest: an explicit
    label beats the container's own ``ENV``, which beats a name that happens to
    carry the word. Nothing matching means development — an unlabelled container
    on a developer's machine is a development container, and guessing
    "production" for it would be the one wrong answer that matters.

    Args:
        labels: The container's Docker labels.
        env_vars: The container's environment, parsed from its config.
        name: Compose project name, or the container name.

    Returns:
        str: One of :data:`ENVIRONMENTS`.
    """
    for key in _ENVIRONMENT_LABEL_KEYS:
        matched = _normalise_environment(labels.get(key))
        if matched:
            return matched

    for key in ("PULSEGRID_ENV", "ENV", "ENVIRONMENT", "APP_ENV", "NODE_ENV"):
        matched = _normalise_environment(env_vars.get(key))
        if matched:
            return matched

    return _environment_from_name(name) or "development"


def _parse_env(raw: list[str] | None) -> dict[str, str]:
    """Parse Docker's ``["KEY=value", ...]`` config into a mapping.

    Only the handful of keys :func:`_classify_environment` reads are ever used,
    and the mapping never leaves this module — a container's environment holds
    its secrets, and none of it belongs on the wire.

    Args:
        raw: The ``Config.Env`` array from an inspect payload.

    Returns:
        dict[str, str]: Parsed variables. Malformed entries are skipped.
    """
    parsed: dict[str, str] = {}
    for entry in raw or []:
        key, separator, value = entry.partition("=")
        if separator:
            parsed[key] = value
    return parsed


def _scheme_for(container_port: int, protocol: str, override: str | None) -> str:
    """Choose the URL scheme a published port should be addressed with.

    Args:
        container_port: The port inside the container — the one that identifies
            the protocol, regardless of which host port it was published on.
        protocol: ``tcp`` or ``udp``.
        override: Value of the container's ``pulsegrid.scheme`` label, if set.

    Returns:
        str: A URL scheme.
    """
    if override:
        return override.strip().lower()
    if protocol != "tcp":
        return protocol
    return _WELL_KNOWN_SCHEMES.get(container_port, "http")


def _landing_path(raw: str | None) -> str:
    """Normalise a container's declared landing path.

    A service's root is not always the thing a person wants to open — this API's
    own root is a 404, while ``/docs`` is the page an operator is actually after.
    Only the service can know that, so it says so with a ``pulsegrid.path``
    label; there is nothing in a port mapping to infer it from, and guessing
    would produce exactly the broken links this feature exists to avoid.

    Args:
        raw: The label value, if the container carries one.

    Returns:
        str: A path beginning with ``/``, or ``""`` for the plain root.
    """
    if not raw:
        return ""
    trimmed = raw.strip().rstrip("/")
    if not trimmed:
        return ""
    return trimmed if trimmed.startswith("/") else f"/{trimmed}"


# --------------------------------------------------------------------------- #
# Container mapping                                                            #
# --------------------------------------------------------------------------- #


def _container_name(inspected: dict[str, Any]) -> str:
    """Strip the leading slash Docker puts on container names."""
    return str(inspected.get("Name") or "").lstrip("/") or str(inspected.get("Id", ""))[:12]


def _health_of(state: dict[str, Any]) -> str:
    """Read a container's healthcheck verdict.

    Two cases are collapsed to ``none``, and both matter. An image that declares
    no healthcheck has no verdict — showing that as "unhealthy" would condemn
    the load generator for a check it was never asked to pass. And a container
    that has stopped keeps whatever its last check said, which Docker itself
    stops reporting once the container is down: "Stopped · Unhealthy" reads as
    two faults when there is one, and the stale half is the louder one.

    Args:
        state: The ``State`` object from an inspect payload.

    Returns:
        str: ``healthy``, ``unhealthy``, ``starting`` or ``none``.
    """
    if str(state.get("Status") or "").lower() != "running":
        return "none"
    health = state.get("Health")
    if not isinstance(health, dict):
        return "none"
    return str(health.get("Status") or "none").lower()


def _ports_of(inspected: dict[str, Any]) -> list[ContainerPort]:
    """Extract every port the container exposes, published or not.

    Docker reports exposed-but-unpublished ports with a ``None`` binding. Those
    are kept: "8001/tcp, not published" is a useful thing to see, and dropping
    them would make an internal-only service look like it has no ports at all.

    Args:
        inspected: A container inspect payload.

    Returns:
        list[ContainerPort]: Ports, ordered by container port then host port.
    """
    raw = (inspected.get("NetworkSettings") or {}).get("Ports") or {}
    ports: list[ContainerPort] = []

    for spec, bindings in raw.items():
        port_text, _, protocol = str(spec).partition("/")
        try:
            container_port = int(port_text)
        except ValueError:
            continue
        protocol = protocol or "tcp"

        if not bindings:
            ports.append(ContainerPort(container_port=container_port, protocol=protocol))
            continue

        # A port bound on both IPv4 and IPv6 is one endpoint, not two. Keep the
        # first binding per host port so the panel does not show 0.0.0.0 and ::
        # as separate rows for what is a single reachable address.
        seen: set[int] = set()
        for binding in bindings:
            try:
                host_port = int(binding.get("HostPort"))
            except (TypeError, ValueError):
                continue
            if host_port in seen:
                continue
            seen.add(host_port)
            ports.append(
                ContainerPort(
                    container_port=container_port,
                    protocol=protocol,
                    host_port=host_port,
                    host_ip=str(binding.get("HostIp") or "0.0.0.0"),
                )
            )

    return sorted(ports, key=lambda port: (port.container_port, port.host_port or 0))


def _endpoints_of(
    ports: list[ContainerPort], labels: dict[str, str], host: str
) -> list[ServiceEndpoint]:
    """Build the addressable endpoints for a container's published ports.

    Args:
        ports: Every port the container exposes.
        labels: The container's Docker labels, read for the optional
            ``pulsegrid.scheme`` and ``pulsegrid.path`` overrides.
        host: Hostname published ports resolve on.

    Returns:
        list[ServiceEndpoint]: One entry per published host port, deduplicated.
    """
    scheme_override = labels.get("pulsegrid.scheme")
    path = _landing_path(labels.get("pulsegrid.path"))

    endpoints: list[ServiceEndpoint] = []
    seen: set[str] = set()

    for port in ports:
        if port.host_port is None:
            continue
        scheme = _scheme_for(port.container_port, port.protocol, scheme_override)
        browsable = scheme in _BROWSABLE
        # A path only means anything to a browser. Appending one to a database
        # address would turn a usable connection string into a broken one.
        suffix = path if browsable else ""
        url = f"{scheme}://{host}:{port.host_port}{suffix}"
        if url in seen:
            continue
        seen.add(url)
        endpoints.append(
            ServiceEndpoint(
                url=url,
                scheme=scheme,
                host=host,
                host_ip=port.host_ip or "0.0.0.0",
                host_port=port.host_port,
                container_port=port.container_port,
                protocol=port.protocol,
                path=suffix,
                browsable=browsable,
                wildcard_bind=(port.host_ip or "") in _WILDCARD_HOST_IPS,
            )
        )

    return endpoints


def _to_container(inspected: dict[str, Any], host: str) -> ContainerRead:
    """Map one inspect payload onto the dashboard's container model.

    Args:
        inspected: A container inspect payload.
        host: Hostname published ports resolve on.

    Returns:
        ContainerRead: The projection sent to the dashboard.
    """
    config = inspected.get("Config") or {}
    state = inspected.get("State") or {}
    labels = {str(key): str(value) for key, value in (config.get("Labels") or {}).items()}
    env_vars = _parse_env(config.get("Env"))

    name = _container_name(inspected)
    project = labels.get("com.docker.compose.project")
    service = labels.get("com.docker.compose.service") or labels.get("pulsegrid.service") or name

    ports = _ports_of(inspected)

    return ContainerRead(
        id=str(inspected.get("Id", ""))[:12],
        name=name,
        service=service,
        project=project,
        image=str(config.get("Image") or ""),
        state=str(state.get("Status") or "unknown").lower(),
        health=_health_of(state),
        environment=_classify_environment(labels, env_vars, project or name),
        created_at=_parse_timestamp(inspected.get("Created")) or datetime.now(UTC),
        started_at=_parse_timestamp(state.get("StartedAt")),
        ports=ports,
        endpoints=_endpoints_of(ports, labels, host),
    )


# --------------------------------------------------------------------------- #
# Reachability                                                                 #
# --------------------------------------------------------------------------- #


def _was_refused(error: Exception) -> bool:
    """Decide whether a failed connection was actively refused.

    ``httpx.ConnectError`` covers two very different outcomes: a host that
    answered "nothing is listening on that port", and a name this process cannot
    resolve at all. Only the first says anything about the *service*; the second
    says the API is not on that container's network, which is a fact about this
    process and not about the link being shown.

    Args:
        error: The exception raised by the request.

    Returns:
        bool: True only when something on the other end refused the connection.
    """
    cause: BaseException | None = error
    while cause is not None:
        if isinstance(cause, socket.gaierror):
            return False
        if isinstance(cause, ConnectionRefusedError):
            return True
        cause = cause.__cause__
    return False


async def _probe_endpoint(
    endpoint: ServiceEndpoint, hosts: list[str], client: httpx.AsyncClient
) -> None:
    """Confirm one HTTP endpoint actually answers, in place.

    The request goes to the *container* address (``http://pulsegrid-web:8080/``),
    never to the published host port: this process runs inside the compose
    network, where ``localhost`` is its own container. Confirming the service
    behind the port is exactly what makes the published URL beside it
    trustworthy.

    ``reachable`` is deliberately three-valued, and the third value is the
    important one. ``True`` means something spoke HTTP back — any status, 404
    included, proves a server is listening. ``False`` means every candidate
    address actively refused, which is a real fault worth showing. Everything
    else — a name that does not resolve, a timeout, a network this process
    cannot see — leaves it ``None``, because "I could not check" and "it is
    broken" are different claims, and a panel that confuses them will condemn a
    working link the first time it is run somewhere unusual.

    Args:
        endpoint: The endpoint to probe. Mutated in place.
        hosts: Candidate container-network names, most likely first.
        client: A shared client with a short timeout.
    """
    # Probe the same path the link opens, so a declared landing path that does
    # not exist is caught here rather than by whoever clicks it.
    target = endpoint.path or "/"
    refusals = 0

    for internal_host in hosts:
        try:
            await client.get(
                f"{endpoint.scheme}://{internal_host}:{endpoint.container_port}{target}"
            )
        except httpx.HTTPError as exc:
            if not _was_refused(exc):
                # Inconclusive. One unresolvable name says nothing about the
                # other, so keep going, but do not let this count as evidence.
                continue
            refusals += 1
        else:
            endpoint.reachable = True
            return

    # Only when every attempt was refused — never on the strength of a name that
    # simply did not resolve.
    if refusals and refusals == len(hosts):
        endpoint.reachable = False


async def _probe_all(containers: list[ContainerRead]) -> None:
    """Probe every running container's HTTP endpoints, concurrently."""
    if not settings.INFRA_PROBE_ENABLED:
        return

    targets: list[tuple[ServiceEndpoint, list[str]]] = []
    for container in containers:
        if container.state != "running":
            continue
        # Compose registers the service name as a network alias; the container
        # name covers containers started outside compose. Duplicates are dropped
        # so a container whose service and name match is not probed twice.
        hosts = list(dict.fromkeys([container.service, container.name]))
        targets.extend((endpoint, hosts) for endpoint in container.endpoints if endpoint.browsable)

    if not targets:
        return

    timeout = httpx.Timeout(settings.INFRA_PROBE_TIMEOUT_SECONDS)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        await asyncio.gather(
            *(_probe_endpoint(endpoint, hosts, client) for endpoint, hosts in targets),
            return_exceptions=True,
        )


# --------------------------------------------------------------------------- #
# Environment grouping                                                         #
# --------------------------------------------------------------------------- #


def _display_status(container: ContainerRead) -> str:
    """One word for how a service is doing, health taking precedence.

    Args:
        container: The container to describe.

    Returns:
        str: ``healthy``, ``unhealthy``, ``starting``, ``running`` or the raw
        Docker state (``exited``, ``paused``, ``restarting``, ...).
    """
    if container.state != "running":
        return container.state
    if container.health in {"healthy", "unhealthy", "starting"}:
        return container.health
    return "running"


def _group_environments(containers: list[ContainerRead]) -> list[EnvironmentGroup]:
    """Collect every browsable endpoint into its environment.

    All three environments are always returned, in pipeline order, so the
    dashboard renders three tabs whether or not each one has anything in it —
    an environment that is empty is information, and a tab that disappears when
    its services stop is a worse dashboard than one that says "nothing running".

    Args:
        containers: Every discovered container.

    Returns:
        list[EnvironmentGroup]: One group per environment.
    """
    buckets: dict[str, list[WebService]] = {name: [] for name in ENVIRONMENTS}
    seen: set[tuple[str, str]] = set()

    for container in containers:
        for endpoint in container.endpoints:
            if not endpoint.browsable:
                continue
            key = (container.environment, endpoint.url)
            if key in seen:
                continue
            seen.add(key)
            buckets[container.environment].append(
                WebService(
                    service=container.service,
                    container=container.name,
                    environment=container.environment,
                    url=endpoint.url,
                    host_port=endpoint.host_port,
                    container_port=endpoint.container_port,
                    scheme=endpoint.scheme,
                    wildcard_bind=endpoint.wildcard_bind,
                    state=container.state,
                    health=container.health,
                    status=_display_status(container),
                    reachable=endpoint.reachable,
                )
            )

    return [
        EnvironmentGroup(
            environment=name,
            label=_ENVIRONMENT_LABELS[name],
            services=sorted(buckets[name], key=lambda item: (item.service, item.host_port)),
        )
        for name in ENVIRONMENTS
    ]


# --------------------------------------------------------------------------- #
# Discovery                                                                    #
# --------------------------------------------------------------------------- #


async def _resolve_scope() -> str | None:
    """Find the compose project to restrict discovery to.

    Asks the daemon which project *this* container belongs to, so the panel
    shows the stack PulseGrid is part of rather than every container on the
    machine. No project name is configured anywhere; moving the stack, renaming
    it or running two copies side by side all work unchanged.

    Returns:
        str | None: The compose project name, or ``None`` to show everything —
        which is also the honest answer when the API is not running in a
        container at all.
    """
    configured = settings.INFRA_PROJECT.strip()
    if configured:
        return None if configured.lower() == "all" else configured

    container_id = self_container_id()
    if container_id is None:
        return None
    try:
        inspected = await engine.inspect(container_id)
    except DockerUnavailable:
        return None
    labels = (inspected.get("Config") or {}).get("Labels") or {}
    return labels.get("com.docker.compose.project")


def _empty(reason: str, host: str) -> InfraSnapshot:
    """Build the well-formed 'nothing to show, and here is why' snapshot."""
    return InfraSnapshot(
        generated_at=datetime.now(UTC),
        available=False,
        reason=reason,
        scope=None,
        host=host,
        containers=[],
        environments=_group_environments([]),
    )


async def _discover() -> InfraSnapshot:
    """Read the live Docker Engine and build a full snapshot.

    Returns:
        InfraSnapshot: Discovered containers and their grouped web endpoints.
        Always well-formed: an unreachable daemon yields an empty snapshot with
        ``available=False`` and a reason, never an error the dashboard has to
        render as a broken panel.
    """
    host = settings.INFRA_PUBLIC_HOST

    try:
        scope = await _resolve_scope()
        summaries = await engine.list_containers()
    except DockerUnavailable as exc:
        logger.info("container discovery unavailable: %s", exc)
        return _empty(str(exc), host)

    if scope is not None:
        summaries = [
            summary
            for summary in summaries
            if (summary.get("Labels") or {}).get("com.docker.compose.project") == scope
        ]

    inspected = await asyncio.gather(
        *(engine.inspect(str(summary.get("Id"))) for summary in summaries),
        return_exceptions=True,
    )

    containers: list[ContainerRead] = []
    for payload in inspected:
        if isinstance(payload, BaseException):
            # A container removed between the list and the inspect. Skipping it
            # is correct — it is genuinely no longer running.
            continue
        if payload:
            containers.append(_to_container(payload, host))

    await _probe_all(containers)

    # Running first, then by service name: the panel's first screenful should be
    # what is up, not whatever the daemon happened to list first.
    containers.sort(key=lambda container: (container.state != "running", container.service))

    return InfraSnapshot(
        generated_at=datetime.now(UTC),
        available=True,
        reason=None,
        scope=scope,
        host=host,
        containers=containers,
        environments=_group_environments(containers),
    )


#: Cached snapshot and the moment it was taken. Every open dashboard polls this
#: endpoint on the same cadence as the SSE stream; without a cache, N tabs would
#: mean N × M inspect calls per tick against a daemon that is not a database.
_cache: tuple[float, InfraSnapshot] | None = None
_cache_lock = asyncio.Lock()


async def discover() -> InfraSnapshot:
    """Return the current infrastructure snapshot, cached briefly.

    The cache window is short enough that a container starting or stopping shows
    up within one dashboard tick, and long enough that a room full of open tabs
    does not hammer the Docker socket.

    Returns:
        InfraSnapshot: The current snapshot.
    """
    global _cache

    ttl = settings.INFRA_CACHE_SECONDS
    now = asyncio.get_running_loop().time()

    cached = _cache
    if cached is not None and now - cached[0] < ttl:
        return cached[1]

    async with _cache_lock:
        # Re-check: a concurrent caller may have refreshed while this one waited.
        cached = _cache
        now = asyncio.get_running_loop().time()
        if cached is not None and now - cached[0] < ttl:
            return cached[1]
        snapshot = await _discover()
        _cache = (now, snapshot)
        return snapshot


def reset_cache() -> None:
    """Drop the cached snapshot. Used by tests and on shutdown."""
    global _cache
    _cache = None
