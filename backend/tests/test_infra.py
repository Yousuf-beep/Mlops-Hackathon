"""Tests for runtime infrastructure discovery.

The Docker Engine is stubbed rather than mocked at the HTTP layer: the payloads
below are trimmed copies of real ``docker inspect`` output, so the mapping is
exercised against the shape the daemon actually sends — including the parts that
are easy to get wrong, like a port bound on both IPv4 and IPv6, an exposed port
with no host binding, and the nanosecond timestamps ``fromisoformat`` refuses.
"""

from __future__ import annotations

import socket
from hashlib import sha256
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.infra import discovery
from app.infra.engine import DockerUnavailable


def _inspect(
    *,
    name: str = "pulsegrid-web",
    service: str = "web",
    project: str | None = "pulsegrid",
    image: str = "pulsegrid-web:dev",
    state: str = "running",
    health: str | None = "healthy",
    ports: dict[str, Any] | None = None,
    labels: dict[str, str] | None = None,
    env: list[str] | None = None,
) -> dict[str, Any]:
    """Build a trimmed but structurally faithful inspect payload."""
    all_labels = dict(labels or {})
    if project is not None:
        all_labels.setdefault("com.docker.compose.project", project)
        all_labels.setdefault("com.docker.compose.service", service)

    container_state: dict[str, Any] = {
        "Status": state,
        "StartedAt": "2026-08-05T03:16:08.594034221Z",
    }
    if health is not None:
        container_state["Health"] = {"Status": health}

    # A distinct 64-hex ID per container name, so a stub holding several of them
    # can tell them apart the way the daemon does.
    container_id = sha256(name.encode()).hexdigest()

    return {
        "Id": container_id,
        "Name": f"/{name}",
        "Created": "2026-08-05T03:16:01.746087113Z",
        "State": container_state,
        "Config": {"Image": image, "Labels": all_labels, "Env": env or []},
        "NetworkSettings": {
            "Ports": ports
            if ports is not None
            else {"8080/tcp": [{"HostIp": "0.0.0.0", "HostPort": "5173"}]}
        },
    }


class _StubEngine:
    """Stands in for the shared Docker Engine handle."""

    def __init__(self, payloads: list[dict[str, Any]], *, fail: str | None = None) -> None:
        self._payloads = payloads
        self._fail = fail

    async def list_containers(self, *, include_stopped: bool = True) -> list[dict[str, Any]]:
        if self._fail:
            raise DockerUnavailable(self._fail)
        return [
            {"Id": payload["Id"], "Labels": payload["Config"]["Labels"]}
            for payload in self._payloads
        ]

    async def inspect(self, container_id: str) -> dict[str, Any]:
        if self._fail:
            raise DockerUnavailable(self._fail)
        return next(
            payload for payload in self._payloads if str(payload["Id"]).startswith(container_id)
        )


@pytest.fixture(autouse=True)
def _isolate_discovery(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give every test a cold cache, no probing and unscoped discovery.

    Probing is off because these tests assert the *mapping*, and a probe would
    make them depend on the machine's network. Scoping is off because
    :func:`_resolve_scope` would otherwise ask the stub about a container ID
    that does not exist in it.
    """
    discovery.reset_cache()
    monkeypatch.setattr(settings, "INFRA_PROBE_ENABLED", False)
    monkeypatch.setattr(settings, "INFRA_PROJECT", "all")
    monkeypatch.setattr(settings, "INFRA_CACHE_SECONDS", 0.0)


def _use(
    monkeypatch: pytest.MonkeyPatch, *payloads: dict[str, Any], fail: str | None = None
) -> None:
    """Point discovery at a stub engine."""
    monkeypatch.setattr(discovery, "engine", _StubEngine(list(payloads), fail=fail))


# --------------------------------------------------------------------------- #
# Parsing                                                                      #
# --------------------------------------------------------------------------- #


def test_nanosecond_timestamps_are_parsed() -> None:
    """Docker's nine-digit fractional seconds are truncated, not rejected."""
    parsed = discovery._parse_timestamp("2026-08-05T03:16:01.746087113Z")

    assert parsed is not None
    assert parsed.year == 2026
    assert parsed.microsecond == 746087


def test_never_started_sentinel_is_not_a_time() -> None:
    """``0001-01-01T00:00:00Z`` means "never", and must not render as a date."""
    assert discovery._parse_timestamp("0001-01-01T00:00:00Z") is None
    assert discovery._parse_timestamp(None) is None
    assert discovery._parse_timestamp("not a timestamp") is None


# --------------------------------------------------------------------------- #
# Ports and endpoints                                                          #
# --------------------------------------------------------------------------- #


def test_dual_stack_binding_is_one_endpoint() -> None:
    """A port bound on IPv4 *and* IPv6 is one address, not two."""
    container = discovery._to_container(
        _inspect(
            ports={
                "8080/tcp": [
                    {"HostIp": "0.0.0.0", "HostPort": "5173"},
                    {"HostIp": "::", "HostPort": "5173"},
                ]
            }
        ),
        "localhost",
    )

    assert [port.host_port for port in container.ports] == [5173]
    assert [endpoint.url for endpoint in container.endpoints] == ["http://localhost:5173"]


def test_exposed_but_unpublished_port_is_kept_without_an_endpoint() -> None:
    """An internal-only port is still a port; it just has no host address."""
    container = discovery._to_container(_inspect(ports={"8001/tcp": None}), "localhost")

    assert len(container.ports) == 1
    assert container.ports[0].host_port is None
    assert container.endpoints == []


def test_a_container_with_no_ports_has_no_endpoints() -> None:
    """The load generator publishes nothing, and that is not an error."""
    container = discovery._to_container(
        _inspect(name="pulsegrid-loadgen", service="loadgen", ports={}, health=None),
        "localhost",
    )

    assert container.ports == []
    assert container.endpoints == []
    assert container.health == "none"


def test_multiple_published_ports_all_become_endpoints() -> None:
    """Every published port gets its own address, ordered by container port."""
    container = discovery._to_container(
        _inspect(
            ports={
                "9090/tcp": [{"HostIp": "0.0.0.0", "HostPort": "9090"}],
                "8080/tcp": [{"HostIp": "0.0.0.0", "HostPort": "5173"}],
            }
        ),
        "localhost",
    )

    assert [endpoint.url for endpoint in container.endpoints] == [
        "http://localhost:5173",
        "http://localhost:9090",
    ]


def test_registered_non_http_ports_are_not_links() -> None:
    """PostgreSQL is addressed as PostgreSQL, and is not offered as a link."""
    container = discovery._to_container(
        _inspect(
            name="pulsegrid-db",
            service="db",
            image="postgres:17-alpine",
            ports={"5432/tcp": [{"HostIp": "0.0.0.0", "HostPort": "5432"}]},
        ),
        "localhost",
    )

    endpoint = container.endpoints[0]
    assert endpoint.scheme == "postgresql"
    assert endpoint.browsable is False
    assert endpoint.url == "postgresql://localhost:5432"


def test_a_port_published_on_a_different_host_port_keeps_its_protocol() -> None:
    """The *container* port identifies the protocol, wherever it is published."""
    container = discovery._to_container(
        _inspect(ports={"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "15432"}]}),
        "localhost",
    )

    endpoint = container.endpoints[0]
    assert endpoint.scheme == "postgresql"
    assert endpoint.host_port == 15432
    # Bound to one interface, so the dashboard must not re-host this link.
    assert endpoint.wildcard_bind is False


def test_a_declared_landing_path_is_appended_to_browsable_links() -> None:
    """A service that knows its root is useless can name a better page."""
    container = discovery._to_container(
        _inspect(
            labels={"pulsegrid.path": "/docs"},
            ports={"8000/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8000"}]},
        ),
        "localhost",
    )

    assert container.endpoints[0].url == "http://localhost:8000/docs"
    assert container.endpoints[0].path == "/docs"


def test_a_landing_path_never_touches_a_non_browsable_address() -> None:
    """A path would turn a connection string into something that will not connect."""
    container = discovery._to_container(
        _inspect(
            labels={"pulsegrid.path": "/docs"},
            ports={"5432/tcp": [{"HostIp": "0.0.0.0", "HostPort": "5432"}]},
        ),
        "localhost",
    )

    assert container.endpoints[0].url == "postgresql://localhost:5432"
    assert container.endpoints[0].path == ""


@pytest.mark.parametrize(
    ("declared", "expected"),
    [("docs", "/docs"), ("/docs/", "/docs"), ("/", ""), ("", ""), ("  ", ""), (None, "")],
)
def test_landing_paths_are_normalised(declared: str | None, expected: str) -> None:
    """A leading slash is added, a trailing one removed, and "/" means none."""
    assert discovery._landing_path(declared) == expected


def test_a_scheme_label_overrides_the_inference() -> None:
    """A service that knows better can say so, and is believed."""
    container = discovery._to_container(
        _inspect(
            labels={"pulsegrid.scheme": "https"},
            ports={"8443/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8443"}]},
        ),
        "localhost",
    )

    assert container.endpoints[0].url == "https://localhost:8443"
    assert container.endpoints[0].browsable is True


# --------------------------------------------------------------------------- #
# Environment classification                                                   #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("labels", "env", "name", "expected"),
    [
        ({"pulsegrid.environment": "production"}, [], "pulsegrid", "production"),
        ({"app.kubernetes.io/environment": "qa"}, [], "pulsegrid", "qa"),
        ({}, ["ENV=prod"], "pulsegrid", "production"),
        ({}, ["ENV=staging"], "pulsegrid", "qa"),
        ({}, [], "pulsegrid-qa", "qa"),
        ({}, [], "acme-production", "production"),
        # Nothing recognisable anywhere: development, never production.
        ({}, [], "pulsegrid", "development"),
        # A whole-segment match only — "quality" is not "qa".
        ({}, [], "pulsegrid-quality", "development"),
    ],
)
def test_environment_classification(
    labels: dict[str, str], env: list[str], name: str, expected: str
) -> None:
    """Environment is read from the most deliberate signal available."""
    container = discovery._to_container(
        _inspect(project=name, labels=labels, env=env),
        "localhost",
    )

    assert container.environment == expected


def test_an_explicit_label_beats_the_containers_own_env() -> None:
    """A stack labelled `qa` is QA even when its processes still say ENV=dev."""
    container = discovery._to_container(
        _inspect(labels={"pulsegrid.environment": "qa"}, env=["ENV=dev"]),
        "localhost",
    )

    assert container.environment == "qa"


def test_container_environment_values_never_reach_the_wire() -> None:
    """Only the derived environment escapes; the variables themselves do not."""
    container = discovery._to_container(
        _inspect(env=["ENV=prod", "JWT_SECRET=super-secret", "POSTGRES_PASSWORD=hunter2"]),
        "localhost",
    )

    assert "hunter2" not in container.model_dump_json()
    assert "JWT_SECRET" not in container.model_dump_json()


# --------------------------------------------------------------------------- #
# Grouping                                                                     #
# --------------------------------------------------------------------------- #


def test_every_environment_is_always_present() -> None:
    """Three groups, in pipeline order, even with nothing running."""
    groups = discovery._group_environments([])

    assert [group.environment for group in groups] == ["development", "qa", "production"]
    assert all(group.services == [] for group in groups)


def test_only_browsable_endpoints_are_grouped() -> None:
    """The database is a container, not a web endpoint."""
    web = discovery._to_container(_inspect(), "localhost")
    database = discovery._to_container(
        _inspect(
            name="pulsegrid-db",
            service="db",
            ports={"5432/tcp": [{"HostIp": "0.0.0.0", "HostPort": "5432"}]},
        ),
        "localhost",
    )

    groups = discovery._group_environments([web, database])
    development = next(group for group in groups if group.environment == "development")

    assert [service.service for service in development.services] == ["web"]


def test_duplicate_addresses_are_collapsed() -> None:
    """Two containers on one address are one entry, not two identical rows."""
    first = discovery._to_container(_inspect(), "localhost")
    second = discovery._to_container(_inspect(name="pulsegrid-web-2"), "localhost")

    groups = discovery._group_environments([first, second])
    development = next(group for group in groups if group.environment == "development")

    assert len(development.services) == 1


def test_a_stopped_container_reports_no_health_verdict() -> None:
    """Docker keeps the last verdict after a stop; showing it is misleading.

    "Stopped · Unhealthy" reads as two problems where there is one, and the
    stale half is the one that draws the eye.
    """
    stopped = discovery._to_container(_inspect(state="exited", health="unhealthy"), "localhost")

    assert stopped.state == "exited"
    assert stopped.health == "none"


def test_status_prefers_health_over_liveness() -> None:
    """A container that is up and failing its healthcheck reads as unhealthy."""
    unhealthy = discovery._to_container(_inspect(health="unhealthy"), "localhost")
    unchecked = discovery._to_container(_inspect(health=None), "localhost")
    stopped = discovery._to_container(_inspect(state="exited", health=None), "localhost")

    assert discovery._display_status(unhealthy) == "unhealthy"
    assert discovery._display_status(unchecked) == "running"
    assert discovery._display_status(stopped) == "exited"


# --------------------------------------------------------------------------- #
# Reachability                                                                 #
# --------------------------------------------------------------------------- #


class _Answering:
    """A client whose requests all succeed."""

    async def get(self, url: str) -> object:
        self.last = url
        return object()


class _Raising:
    """A client whose requests all fail the same way."""

    def __init__(self, error: Exception) -> None:
        self._error = error

    async def get(self, url: str) -> object:
        raise self._error


def _endpoint(path: str = "") -> Any:
    """A lone browsable endpoint to probe."""
    container = discovery._to_container(
        _inspect(
            labels={"pulsegrid.path": path} if path else {},
            ports={"8080/tcp": [{"HostIp": "0.0.0.0", "HostPort": "5173"}]},
        ),
        "localhost",
    )
    return container.endpoints[0]


def _refused() -> httpx.ConnectError:
    """A connect error caused by an actual refusal, as httpx wraps one."""
    error = httpx.ConnectError("refused")
    error.__cause__ = ConnectionRefusedError(111, "Connection refused")
    return error


def _unresolvable() -> httpx.ConnectError:
    """A connect error caused by a name that does not resolve."""
    error = httpx.ConnectError("name or service not known")
    error.__cause__ = socket.gaierror(-2, "Name or service not known")
    return error


async def test_a_response_of_any_status_proves_reachability() -> None:
    """A 404 still proves a server is listening and speaking HTTP."""
    endpoint = _endpoint()

    await discovery._probe_endpoint(endpoint, ["web"], _Answering())  # type: ignore[arg-type]

    assert endpoint.reachable is True


async def test_the_probe_follows_the_declared_landing_path() -> None:
    """The link that gets shown is the link that gets checked."""
    endpoint = _endpoint("/docs")
    client = _Answering()

    await discovery._probe_endpoint(endpoint, ["api"], client)  # type: ignore[arg-type]

    assert client.last == "http://api:8080/docs"


async def test_a_refused_connection_is_reported_as_a_fault() -> None:
    """Nothing listening behind a published port is worth showing."""
    endpoint = _endpoint()

    await discovery._probe_endpoint(endpoint, ["web"], _Raising(_refused()))  # type: ignore[arg-type]

    assert endpoint.reachable is False


async def test_an_unresolvable_name_is_never_reported_as_a_fault() -> None:
    """A container this process cannot see is not a broken link.

    This is the case that matters: the API not being on the probed container's
    network says nothing about whether the published port works from a browser,
    and condemning the link on that basis would be a false alarm on every host
    with a segmented network.
    """
    endpoint = _endpoint()

    await discovery._probe_endpoint(endpoint, ["web"], _Raising(_unresolvable()))  # type: ignore[arg-type]

    assert endpoint.reachable is None


async def test_a_timeout_is_inconclusive() -> None:
    """A slow service is not an absent one."""
    endpoint = _endpoint()
    timeout = httpx.ConnectTimeout("timed out")

    await discovery._probe_endpoint(endpoint, ["web"], _Raising(timeout))  # type: ignore[arg-type]

    assert endpoint.reachable is None


async def test_probing_is_skipped_for_stopped_containers(monkeypatch: pytest.MonkeyPatch) -> None:
    """A stopped container has nothing to answer, and is never asked.

    Probing is switched on for this one, so the early return is what keeps it
    off the network — not the fixture that disables probing everywhere else.
    """
    monkeypatch.setattr(settings, "INFRA_PROBE_ENABLED", True)
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **_: pytest.fail("a stopped container must not be probed")
    )
    stopped = discovery._to_container(_inspect(state="exited"), "localhost")

    await discovery._probe_all([stopped])

    assert stopped.endpoints[0].reachable is None


# --------------------------------------------------------------------------- #
# Routes                                                                       #
# --------------------------------------------------------------------------- #


async def test_snapshot_reports_the_running_stack(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The snapshot carries both projections of one discovery pass."""
    _use(monkeypatch, _inspect())

    body = client.get("/v1/infra/snapshot").json()

    assert body["available"] is True
    assert body["reason"] is None
    assert [container["service"] for container in body["containers"]] == ["web"]
    development = body["environments"][0]
    assert development["environment"] == "development"
    assert development["services"][0]["url"] == "http://localhost:5173"


async def test_an_unreachable_runtime_is_a_result_not_an_error(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing socket yields an explained empty panel, never a 5xx."""
    _use(monkeypatch, fail="cannot reach the Docker Engine (permission denied)")

    response = client.get("/v1/infra/snapshot")

    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert "permission denied" in body["reason"]
    assert body["containers"] == []
    # The tabs still exist, so the dashboard renders its empty states rather
    # than a panel that has lost its shape.
    assert len(body["environments"]) == 3


async def test_stopped_containers_are_listed_after_running_ones(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stopped service is shown as stopped, not omitted — and sorted last."""
    _use(
        monkeypatch,
        _inspect(name="pulsegrid-db", service="db", state="exited", health=None, ports={}),
        _inspect(),
    )

    body = client.get("/v1/infra/snapshot").json()

    assert [container["state"] for container in body["containers"]] == ["running", "exited"]


async def test_containers_and_environments_are_projections_of_the_snapshot(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The narrow routes return exactly what the snapshot carries."""
    _use(monkeypatch, _inspect())

    snapshot = client.get("/v1/infra/snapshot").json()

    assert client.get("/v1/infra/containers").json() == snapshot["containers"]
    assert client.get("/v1/infra/environments").json() == snapshot["environments"]


async def test_discovery_is_cached_between_requests(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Many open dashboards cost one look at the socket, not one each."""
    monkeypatch.setattr(settings, "INFRA_CACHE_SECONDS", 60.0)
    stub = _StubEngine([_inspect()])
    calls = 0

    original = stub.list_containers

    async def counted(**kwargs: object) -> list[dict[str, Any]]:
        nonlocal calls
        calls += 1
        return await original(**kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(stub, "list_containers", counted)
    monkeypatch.setattr(discovery, "engine", stub)

    for _ in range(3):
        assert client.get("/v1/infra/snapshot").json()["available"] is True

    assert calls == 1
