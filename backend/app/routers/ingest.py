"""Collection routes: the SDK ingest endpoint and the transparent reverse proxy.

Phase 1 ships the routes, their contracts and their OpenAPI entries only.

Planned behaviour (phase 2):
    * ``POST /v1/ingest`` validates a batch of :class:`~app.schemas.IngestEvent`
      records and bulk-inserts them into ``request_log``.
    * ``/proxy/{path}`` resolves the target from ``api_registry``, forwards the
      request with ``httpx`` preserving method, headers and body, streams the
      upstream response back untouched, and appends one ``request_log`` row
      recording latency, status and payload sizes.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, status

from app.routers import NOT_IMPLEMENTED_RESPONSE, not_implemented
from app.schemas import IngestAccepted, IngestEvent

router = APIRouter(prefix="/v1", tags=["ingest"])

#: The proxy is intentionally *not* under ``/v1``: it must mirror upstream
#: paths verbatim so callers can repoint a base URL and change nothing else.
proxy_router = APIRouter(tags=["proxy"])


@router.post(
    "/ingest",
    response_model=IngestAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest a batch of client-observed API calls (phase 2)",
    responses=NOT_IMPLEMENTED_RESPONSE,
)
def ingest_events(events: list[IngestEvent]) -> IngestAccepted:
    """Persist a batch of externally observed calls into ``request_log``.

    Args:
        events: The observations reported by a PulseGrid SDK.

    Returns:
        IngestAccepted: Count of persisted events.

    Raises:
        HTTPException: Always 501 in phase 1.
    """
    raise not_implemented("ingest.batch")


#: Verbs the proxy relays. Registered one route per verb rather than a single
#: multi-method route so each gets a distinct OpenAPI ``operationId`` — a
#: single ``api_route`` shares one id across verbs and FastAPI warns about it.
PROXY_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")


def proxy(path: str, request: Request) -> None:
    """Forward a request to its registered upstream and record the call.

    Args:
        path: Everything after ``/proxy/``, forwarded verbatim upstream.
        request: The inbound request, whose method, headers and body are
            replayed against the upstream.

    Raises:
        HTTPException: Always 501 in phase 1.
    """
    raise not_implemented("proxy.forward")


for _method in PROXY_METHODS:
    proxy_router.add_api_route(
        "/proxy/{path:path}",
        proxy,
        methods=[_method],
        name=f"proxy_{_method.lower()}",
        operation_id=f"proxy_{_method.lower()}",
        summary=f"Transparent reverse proxy ({_method}) to a registered upstream (phase 2)",
        responses=NOT_IMPLEMENTED_RESPONSE,
    )
