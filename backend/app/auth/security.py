"""Pure security primitives: password hashing and JWT encode/decode.

This module has no FastAPI or database imports on purpose — it is a leaf
dependency that can be unit-tested in isolation and reused by scripts.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

#: bcrypt is deliberate: it is adaptive, salted per-hash and resistant to
#: GPU cracking. ``deprecated="auto"`` lets us rotate to a newer scheme later
#: without invalidating existing digests.
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

#: bcrypt truncates anything past 72 bytes; reject rather than silently ignore.
BCRYPT_MAX_BYTES = 72


class TokenError(Exception):
    """Raised when a token is malformed, expired or fails signature checks."""


def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt.

    Args:
        password: The plaintext password.

    Returns:
        str: The bcrypt digest, safe to persist.

    Raises:
        ValueError: If the password exceeds bcrypt's 72-byte input limit.
    """
    if len(password.encode("utf-8")) > BCRYPT_MAX_BYTES:
        raise ValueError(f"password must be at most {BCRYPT_MAX_BYTES} bytes")
    return _pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a stored digest.

    Args:
        plain_password: The candidate plaintext password.
        hashed_password: The stored bcrypt digest.

    Returns:
        bool: ``True`` if the password matches, ``False`` otherwise. A
        malformed or unknown-scheme digest returns ``False`` rather than
        raising, so a corrupt row cannot turn into a 500.
    """
    try:
        return _pwd_context.verify(plain_password, hashed_password)
    except (ValueError, TypeError):
        return False


def create_access_token(
    subject: str | int,
    role: str,
    expires_delta: timedelta | None = None,
) -> tuple[str, int]:
    """Issue a signed JWT access token.

    Args:
        subject: The user id the token identifies. Coerced to ``str`` because
            RFC 7519 requires ``sub`` to be a string.
        role: The user's role, embedded so authorisation checks avoid a
            database round-trip on every request.
        expires_delta: Custom lifetime. Defaults to
            ``settings.ACCESS_TOKEN_EXPIRE_MINUTES``.

    Returns:
        tuple[str, int]: The encoded token and its lifetime in seconds.
    """
    lifetime = expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    now = datetime.now(UTC)
    expire = now + lifetime
    claims: dict[str, Any] = {
        "sub": str(subject),
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    token = jwt.encode(claims, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return token, int(lifetime.total_seconds())


def decode_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT access token.

    Args:
        token: The encoded JWT.

    Returns:
        dict[str, Any]: The verified claim set.

    Raises:
        TokenError: If the signature is invalid, the token has expired, or the
            required ``sub`` claim is missing.
    """
    try:
        claims: dict[str, Any] = jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
    except JWTError as exc:
        raise TokenError(str(exc)) from exc
    if not claims.get("sub"):
        raise TokenError("token is missing the 'sub' claim")
    return claims
