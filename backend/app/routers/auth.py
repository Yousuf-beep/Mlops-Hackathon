"""Authentication routes: registration and login.

Implemented in full — everything else in PulseGrid is gated behind a token, so
this is the foundation the rest of the API is built on.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.auth.dependencies import CurrentUser
from app.auth.security import create_access_token, hash_password, verify_password
from app.database import get_session
from app.models import User
from app.schemas import ErrorResponse, Token, UserCreate, UserLogin, UserRead

router = APIRouter(prefix="/v1/auth", tags=["auth"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new operator account",
    responses={409: {"model": ErrorResponse, "description": "Email already registered"}},
)
def register(payload: UserCreate, session: SessionDep) -> User:
    """Create a new user account.

    Args:
        payload: Email, plaintext password and requested role.
        session: Active database session.

    Returns:
        User: The created user, serialised without its password digest.

    Raises:
        HTTPException: 409 if the email is already registered.
    """
    existing = session.exec(select(User).where(User.email == payload.email)).first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="email already registered",
        )

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role=payload.role,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@router.post(
    "/login",
    response_model=Token,
    summary="Exchange credentials for a JWT access token",
    responses={401: {"model": ErrorResponse, "description": "Invalid credentials"}},
)
def login(payload: UserLogin, session: SessionDep) -> Token:
    """Authenticate and issue an access token.

    The same 401 is returned for an unknown email and for a wrong password so
    the endpoint cannot be used to enumerate registered accounts.

    Args:
        payload: Email and plaintext password.
        session: Active database session.

    Returns:
        Token: The signed JWT and its lifetime.

    Raises:
        HTTPException: 401 if the credentials do not match.
    """
    user = session.exec(select(User).where(User.email == payload.email)).first()
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token, expires_in = create_access_token(subject=user.id or 0, role=str(user.role))
    return Token(access_token=token, expires_in=expires_in)


@router.get("/me", response_model=UserRead, summary="Return the authenticated user")
def read_me(current_user: CurrentUser) -> User:
    """Return the account attached to the presented token.

    Args:
        current_user: The authenticated user.

    Returns:
        User: The caller's own record.
    """
    return current_user
