"""FastAPI authentication dependencies.

PulseGrid uses a plain ``Authorization: Bearer <jwt>`` header rather than
OAuth2 password flow: the API is JSON-only, and ``HTTPBearer`` still renders an
"Authorize" button in Swagger UI, so nothing is lost in developer experience.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session, select

from app.auth.security import TokenError, decode_token
from app.database import get_session
from app.models import User, UserRole

bearer_scheme = HTTPBearer(auto_error=False, description="PulseGrid JWT access token")

_CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[Session, Depends(get_session)],
) -> User:
    """Resolve the authenticated user from the ``Authorization`` header.

    Args:
        credentials: Parsed bearer credentials, or ``None`` when the header is
            absent or not a bearer scheme.
        session: Active database session.

    Returns:
        User: The authenticated, still-existing user record.

    Raises:
        HTTPException: 401 if the header is missing, the token is invalid or
            expired, or the subject no longer exists.
    """
    if credentials is None:
        raise _CREDENTIALS_EXCEPTION

    try:
        claims = decode_token(credentials.credentials)
    except TokenError as exc:
        raise _CREDENTIALS_EXCEPTION from exc

    try:
        user_id = int(claims["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise _CREDENTIALS_EXCEPTION from exc

    user = session.exec(select(User).where(User.id == user_id)).first()
    if user is None:
        raise _CREDENTIALS_EXCEPTION
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_current_admin(user: CurrentUser) -> User:
    """Require that the authenticated user holds the ``admin`` role.

    Args:
        user: The authenticated user, injected by :func:`get_current_user`.

    Returns:
        User: The authenticated administrator.

    Raises:
        HTTPException: 403 if the user is not an administrator.
    """
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="administrator role required",
        )
    return user


CurrentAdmin = Annotated[User, Depends(get_current_admin)]
