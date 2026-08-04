"""API-registry CRUD routes.

The registry is the catalogue of APIs PulseGrid monitors. Rows are scoped to
their owner: a ``viewer`` sees and edits only the APIs it registered, while an
``admin`` sees the whole fleet.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from app.auth.dependencies import CurrentUser
from app.database import get_session
from app.models import ApiRegistry, User, UserRole
from app.schemas import ApiCreate, ApiRead, ApiUpdate, ErrorResponse

router = APIRouter(prefix="/v1/apis", tags=["registry"])

SessionDep = Annotated[Session, Depends(get_session)]

_NOT_FOUND = {404: {"model": ErrorResponse, "description": "API not found"}}
_AUTH_RESPONSES = {401: {"model": ErrorResponse, "description": "Missing or invalid token"}}


def _get_owned_api(api_id: int, session: Session, user: User) -> ApiRegistry:
    """Fetch an API the caller is allowed to act on.

    Args:
        api_id: Primary key of the registry row.
        session: Active database session.
        user: The authenticated caller.

    Returns:
        ApiRegistry: The requested row.

    Raises:
        HTTPException: 404 if the row does not exist, or if it exists but
            belongs to another user. Returning 404 rather than 403 avoids
            leaking the existence of other tenants' APIs.
    """
    api = session.get(ApiRegistry, api_id)
    if api is None or (user.role != UserRole.ADMIN and api.owner_user_id != user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="api not found")
    return api


@router.post(
    "",
    response_model=ApiRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register an API for monitoring",
    responses=_AUTH_RESPONSES,
)
def create_api(payload: ApiCreate, session: SessionDep, current_user: CurrentUser) -> ApiRegistry:
    """Register a new API, owned by the caller.

    Args:
        payload: Registration attributes including SLO targets.
        session: Active database session.
        current_user: The authenticated caller, who becomes the owner.

    Returns:
        ApiRegistry: The newly created registry row.
    """
    api = ApiRegistry(**payload.model_dump(), owner_user_id=current_user.id or 0)
    session.add(api)
    session.commit()
    session.refresh(api)
    return api


@router.get(
    "",
    response_model=list[ApiRead],
    summary="List registered APIs",
    responses=_AUTH_RESPONSES,
)
def list_apis(
    session: SessionDep,
    current_user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=200, description="Page size.")] = 50,
    offset: Annotated[int, Query(ge=0, description="Rows to skip.")] = 0,
) -> list[ApiRegistry]:
    """List the APIs visible to the caller, newest first.

    Args:
        session: Active database session.
        current_user: The authenticated caller.
        limit: Maximum number of rows to return.
        offset: Number of rows to skip, for pagination.

    Returns:
        list[ApiRegistry]: The caller's APIs, or all APIs for an admin.
    """
    statement = select(ApiRegistry)
    if current_user.role != UserRole.ADMIN:
        statement = statement.where(ApiRegistry.owner_user_id == current_user.id)
    statement = statement.order_by(ApiRegistry.id.desc()).offset(offset).limit(limit)  # type: ignore[union-attr]
    return list(session.exec(statement).all())


@router.get(
    "/{api_id}",
    response_model=ApiRead,
    summary="Fetch one registered API",
    responses={**_AUTH_RESPONSES, **_NOT_FOUND},
)
def get_api(api_id: int, session: SessionDep, current_user: CurrentUser) -> ApiRegistry:
    """Return a single registered API.

    Args:
        api_id: Primary key of the registry row.
        session: Active database session.
        current_user: The authenticated caller.

    Returns:
        ApiRegistry: The requested row.
    """
    return _get_owned_api(api_id, session, current_user)


@router.patch(
    "/{api_id}",
    response_model=ApiRead,
    summary="Partially update a registered API",
    responses={**_AUTH_RESPONSES, **_NOT_FOUND},
)
def update_api(
    api_id: int,
    payload: ApiUpdate,
    session: SessionDep,
    current_user: CurrentUser,
) -> ApiRegistry:
    """Apply a partial update to a registered API.

    Args:
        api_id: Primary key of the registry row.
        payload: Fields to change; unset fields are left untouched.
        session: Active database session.
        current_user: The authenticated caller.

    Returns:
        ApiRegistry: The updated row.
    """
    api = _get_owned_api(api_id, session, current_user)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(api, field, value)
    session.add(api)
    session.commit()
    session.refresh(api)
    return api


@router.delete(
    "/{api_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Deregister an API",
    responses={**_AUTH_RESPONSES, **_NOT_FOUND},
)
def delete_api(api_id: int, session: SessionDep, current_user: CurrentUser) -> None:
    """Remove an API from the registry.

    Args:
        api_id: Primary key of the registry row.
        session: Active database session.
        current_user: The authenticated caller.
    """
    api = _get_owned_api(api_id, session, current_user)
    session.delete(api)
    session.commit()
