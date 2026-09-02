from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import bcrypt
from jose import ExpiredSignatureError, JWTError, jwt

from app.core.config import settings

TokenType = Literal["access", "refresh"]


class TokenError(ValueError):
    """A token that cannot be trusted — malformed, wrong signature, or expired."""


class TokenExpiredError(TokenError):
    """Signature was valid but the token has aged out.

    Kept separate from :class:`TokenError` so the caller can tell the guest to
    sign in again rather than implying their credentials were wrong.
    """


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_token(
    subject: str,
    token_type: TokenType,
    expires_delta: timedelta | None = None,
    jti: str | None = None,
) -> tuple[str, datetime]:
    if expires_delta is None:
        if token_type == "access":  # nosec B105 — JWT token type, not a password
            expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        else:
            expires_delta = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    now = datetime.now(UTC)
    expires_at = now + expires_delta
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": expires_at,
    }
    if jti is not None:
        payload["jti"] = jti
    return (
        jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM),
        expires_at,
    )


def decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
    except ExpiredSignatureError as exc:
        raise TokenExpiredError("Token expired") from exc
    except JWTError as exc:
        raise TokenError("Invalid token") from exc
