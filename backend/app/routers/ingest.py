"""Collection routes: the SDK ingest endpoint and the transparent reverse proxy.

Two collection paths feed ``request_log``:

* ``POST /v1/ingest`` — an SDK reports calls it observed itself. Cheap, but it
  only sees what the caller instruments.
* ``/proxy/{slug}/{path}`` — PulseGrid sits in the request path and measures
  every call itself. The proxy resolves ``slug`` against ``api_registry``,
  replays method, headers and body against the registered upstream with
  ``httpx``, returns the upstream response untouched, and appends one
  ``request_log`` row recording latency, status and payload sizes.

The proxy is intentionally *not* mounted under ``/v1``: it mirrors upstream
paths verbatim so a caller can repoint a base URL and change nothing else.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlmodel import Session, select

from app.config import settings
from app.database import get_session
from app.models import ApiRegistry, LogSource, RequestLog, utcnow
from app.schemas import ErrorResponse, IngestAccepted, IngestEvent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["ingest"])

#: The proxy is intentionally *not* under ``/v1``: it must mirror upstream
#: paths verbatim so callers can repoint a base URL and change nothing else.
proxy_router = APIRouter(tags=["proxy"])

SessionDep = Annotated[Session, Depends(get_session)]

#: Hop-by-hop headers that describe *this* connection rather than the message.
#: Relaying them corrupts the proxied exchange — most visibly ``content-length``
#: and ``transfer-encoding``, which httpx recomputes for the upstream request
#: and Starlette recomputes for the downstream response.
_HOP_BY_HOP = frozenset(
    {
        "connection",
        "content-encoding",
        "content-length",
        "host",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
)

#: Path segments that are obviously identifiers get folded into a placeholder so
#: rollups group by *route* rather than by every distinct id. Without this,
#: ``/users/1`` and ``/users/2`` become separate series and every aggregate is
#: computed over a sample size of one.
_NUMERIC_SEGMENT = re.compile(r"^\d+$")
_UUID_SEGMENT = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)
_HEXISH_SEGMENT = re.compile(r"^[0-9a-f]{16,}$", re.IGNORECASE)


def normalise_endpoint(path: str) -> str:
    """Fold a concrete request path into a route template.

    Args:
        path: The raw path, with or without a leading slash.

    Returns:
        str: The template, e.g. ``/users/42/orders`` → ``/users/{id}/orders``.
        An empty path normalises to ``/``.
    """
    stripped = path.strip("/")
    if not stripped:
        return "/"
    segments: list[str] = []
    for segment in stripped.split("/"):
        if _NUMERIC_SEGMENT.match(segment):
            segments.append("{id}")
        elif _UUID_SEGMENT.match(segment):
            segments.append("{uuid}")
        elif _HEXISH_SEGMENT.match(segment):
            segments.append("{hash}")
        else:
            segments.append(segment)
    return "/" + "/".join(segments)


def registry_slug(base_url: str) -> str:
    """Derive the proxy mount slug from a registry row's ``base_url``.

    ``base_url`` is stored loosely (``/payments``, ``payments``, or even a full
    URL), so the slug is the first meaningful path component, lowercased.

    Args:
        base_url: The registered public-facing base URL or path.

    Returns:
        str: The slug the proxy matches the first path segment against.
    """
    without_scheme = base_url.split("://", 1)[-1]
    path = without_scheme.split("/", 1)[1] if "/" in without_scheme else without_scheme
    return path.strip("/").split("/")[0].lower()


def resolve_api(slug: str, session: Session) -> ApiRegistry:
    """Find the registry row a proxy request belongs to.

    Args:
        slug: First path segment of the proxy request.
        session: Active database session.

    Returns:
        ApiRegistry: The matching registry row.

    Raises:
        HTTPException: 404 when no registered API claims that slug.
    """
    for api in session.exec(select(ApiRegistry)).all():
        if registry_slug(api.base_url) == slug.lower():
            return api
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"no registered api is mounted at /proxy/{slug}",
    )


@router.post(
    "/ingest",
    response_model=IngestAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest a batch of client-observed API calls",
    responses={404: {"model": ErrorResponse, "description": "Unknown api_id"}},
)
def ingest_events(events: list[IngestEvent], session: SessionDep) -> IngestAccepted:
    """Persist a batch of externally observed calls into ``request_log``.

    Every distinct ``api_id`` is validated against the registry first, so a typo
    fails loudly instead of writing orphaned rows no dashboard will ever show.

    Args:
        events: The observations reported by a PulseGrid SDK.
        session: Active database session.

    Returns:
        IngestAccepted: Count of persisted events.

    Raises:
        HTTPException: 404 if any event references an unregistered ``api_id``.
    """
    if not events:
        return IngestAccepted(accepted=0)

    for api_id in {event.api_id for event in events}:
        if session.get(ApiRegistry, api_id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"unknown api_id: {api_id}",
            )

    rows = [
        RequestLog(
            time=event.time or utcnow(),
            api_id=event.api_id,
            endpoint=normalise_endpoint(event.endpoint),
            method=event.method.upper(),
            status_code=event.status_code,
            latency_ms=event.latency_ms,
            request_bytes=event.request_bytes,
            response_bytes=event.response_bytes,
            client_ip=event.client_ip,
            is_error=event.status_code >= 500,
            source=LogSource.SDK,
        )
        for event in events
    ]
    session.add_all(rows)
    session.commit()
    logger.debug("ingested %d event(s)", len(rows))
    return IngestAccepted(accepted=len(rows))


def record_call(
    session: Session,
    *,
    api_id: int,
    endpoint: str,
    method: str,
    status_code: int,
    latency_ms: float,
    source: LogSource,
    request_bytes: int | None = None,
    response_bytes: int | None = None,
    client_ip: str | None = None,
) -> RequestLog:
    """Append one observation to ``request_log``.

    Shared by the proxy and the active prober so both produce identically
    shaped rows and the rollup job never has to care which collector wrote them.

    Args:
        session: Active database session.
        api_id: Registry id the call belongs to.
        endpoint: Already-normalised route template.
        method: HTTP verb.
        status_code: Response status; ``5xx`` and ``0`` count as errors.
        latency_ms: Measured end-to-end duration.
        source: Which collector observed the call.
        request_bytes: Request payload size, when known.
        response_bytes: Response payload size, when known.
        client_ip: Caller address, when known.

    Returns:
        RequestLog: The persisted row.
    """
    row = RequestLog(
        time=utcnow(),
        api_id=api_id,
        endpoint=endpoint,
        method=method.upper(),
        status_code=status_code,
        latency_ms=latency_ms,
        request_bytes=request_bytes,
        response_bytes=response_bytes,
        client_ip=client_ip,
        is_error=status_code >= 500 or status_code == 0,
        source=source,
    )
    session.add(row)
    session.commit()
    return row


#: Verbs the proxy relays. Registered one route per verb rather than a single
#: multi-method route so each gets a distinct OpenAPI ``operationId`` — a
#: single ``api_route`` shares one id across verbs and FastAPI warns about it.
PROXY_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")

#: Status recorded when the upstream never answered (DNS failure, refused
#: connection, timeout). 502 is what the caller sees, and it is an error for
#: every Golden-Signal purpose, so it is also what gets logged.
_UPSTREAM_FAILURE_STATUS = 502


async def proxy(path: str, request: Request, session: SessionDep) -> Response:
    """Forward a request to its registered upstream and record the call.

    The first path segment selects the registered API; everything after it is
    forwarded verbatim. Transport failures are recorded too — an upstream that
    stopped answering is exactly the event the dashboard must show, so it
    becomes a logged 502 rather than a dropped measurement.

    Args:
        path: Everything after ``/proxy/``: ``{slug}/{upstream path}``.
        request: The inbound request, whose method, headers and body are
            replayed against the upstream.
        session: Active database session.

    Returns:
        Response: The upstream response, status and body untouched.

    Raises:
        HTTPException: 404 when the slug matches no registered API.
    """
    slug, _, remainder = path.partition("/")
    api = resolve_api(slug, session)

    target = f"{api.upstream_url.rstrip('/')}/{remainder.lstrip('/')}".rstrip("/")
    if request.url.query:
        target = f"{target}?{request.url.query}"

    body = await request.body()
    forward_headers = {k: v for k, v in request.headers.items() if k.lower() not in _HOP_BY_HOP}
    endpoint = normalise_endpoint(remainder)
    client_ip = request.client.host if request.client else None

    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=settings.PROXY_TIMEOUT_SECONDS) as client:
            upstream = await client.request(
                request.method,
                target,
                headers=forward_headers,
                content=body or None,
            )
        latency_ms = (time.perf_counter() - started) * 1000.0
        status_code = upstream.status_code
        payload = upstream.content
        response_bytes = len(payload)
        media_type = upstream.headers.get("content-type")
        passthrough = {k: v for k, v in upstream.headers.items() if k.lower() not in _HOP_BY_HOP}
    except httpx.HTTPError as exc:
        latency_ms = (time.perf_counter() - started) * 1000.0
        status_code = _UPSTREAM_FAILURE_STATUS
        payload = b'{"detail":"upstream unreachable"}'
        response_bytes = 0
        media_type = "application/json"
        passthrough = {}
        logger.warning("proxy upstream failure for %s: %s", target, exc)

    record_call(
        session,
        api_id=api.id or 0,
        endpoint=endpoint,
        method=request.method,
        status_code=status_code,
        latency_ms=latency_ms,
        source=LogSource.PROXY,
        request_bytes=len(body) or None,
        response_bytes=response_bytes or None,
        client_ip=client_ip,
    )

    return Response(
        content=payload,
        status_code=status_code,
        headers=passthrough,
        media_type=media_type,
    )


for _method in PROXY_METHODS:
    proxy_router.add_api_route(
        "/proxy/{path:path}",
        proxy,
        methods=[_method],
        name=f"proxy_{_method.lower()}",
        operation_id=f"proxy_{_method.lower()}",
        summary=f"Transparent reverse proxy ({_method}) to a registered upstream",
        responses={404: {"model": ErrorResponse, "description": "No API mounted at that slug"}},
    )
