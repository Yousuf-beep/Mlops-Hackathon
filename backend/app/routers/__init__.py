"""HTTP routers.

Every router is mounted under ``/v1`` except the reverse proxy (``/proxy``),
which must stay path-transparent for the upstreams it fronts, and ``/health``,
which is defined on the app itself so orchestrators can probe a stable path.
"""

from fastapi import HTTPException, status

from app.schemas import ErrorResponse

#: Reusable OpenAPI ``responses`` entry for every phase-1 stub, so the
#: generated docs advertise the 501 instead of implying the route works.
NOT_IMPLEMENTED_RESPONSE: dict[int | str, dict[str, object]] = {
    501: {"model": ErrorResponse, "description": "Planned for a later phase"}
}


def not_implemented(name: str) -> HTTPException:
    """Build the canonical 501 raised by every not-yet-built endpoint.

    Args:
        name: Short identifier of the missing capability, e.g.
            ``"analytics.latency"``.

    Returns:
        HTTPException: A 501 with body ``{"detail": "not implemented: <name>"}``.
    """
    return HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=f"not implemented: {name}",
    )
