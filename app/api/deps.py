import uuid
from collections.abc import Callable, Coroutine
from typing import Annotated, Any, Literal

from fastapi import Depends, Header, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import decode_token
from app.models.user import User, UserRole
from app.services.user_service import UserService, get_user_service

SUPPORTED_LOCALES: tuple[str, ...] = ("uz", "ru", "en")
DEFAULT_LOCALE = "en"

Locale = Literal["uz", "ru", "en"]

bearer_scheme = HTTPBearer(auto_error=True)
optional_bearer_scheme = HTTPBearer(auto_error=False)


def _resolve_user_id(credentials: HTTPAuthorizationCredentials) -> uuid.UUID:
    error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        claims = decode_token(credentials.credentials)
    except ValueError as exc:
        raise error from exc
    if claims.get("type") != "access":
        raise error
    try:
        return uuid.UUID(claims["sub"])
    except (KeyError, ValueError) as exc:
        raise error from exc


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    users: Annotated[UserService, Depends(get_user_service)],
) -> User:
    user_id = _resolve_user_id(credentials)
    user = await users.get_by_id(user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_optional_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(optional_bearer_scheme)
    ],
    users: Annotated[UserService, Depends(get_user_service)],
) -> User | None:
    if credentials is None:
        return None
    user_id = _resolve_user_id(credentials)
    user = await users.get_by_id(user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_optional_user)]


def _parse_accept_language(header: str) -> str | None:
    """Parse an Accept-Language header and return the first supported locale.

    Handles formats like "en-US,en;q=0.9,ru;q=0.8" by stripping region tags
    and q-values, then matching against SUPPORTED_LOCALES in order of preference.
    """
    for part in header.split(","):
        tag = part.split(";", 1)[0].strip().lower()
        primary = tag.split("-", 1)[0]
        if primary in SUPPORTED_LOCALES:
            return primary
    return None


def get_locale(
    lang: Annotated[str | None, Query(description="Locale (uz, ru, en)")] = None,
    accept_language: Annotated[str | None, Header()] = None,
) -> Locale:
    """Resolve the request locale.

    Priority: ?lang= query > Accept-Language header > DEFAULT_LOCALE.
    Unsupported values fall through to the next source.
    """
    if lang:
        candidate = lang.strip().lower()
        if candidate in SUPPORTED_LOCALES:
            return candidate  # type: ignore[return-value]
    if accept_language:
        resolved = _parse_accept_language(accept_language)
        if resolved is not None:
            return resolved  # type: ignore[return-value]
    return DEFAULT_LOCALE  # type: ignore[return-value]


def get_include_translations(
    include_translations: Annotated[
        bool,
        Query(description="Return full {uz,ru,en} dicts instead of resolved strings"),
    ] = False,
) -> bool:
    return include_translations


LocaleDep = Annotated[Locale, Depends(get_locale)]
IncludeTranslationsDep = Annotated[bool, Depends(get_include_translations)]


def require_roles(
    *roles: UserRole,
) -> Callable[[User], Coroutine[Any, Any, User]]:
    allowed = set(roles)

    async def _checker(user: CurrentUser) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user

    return _checker
