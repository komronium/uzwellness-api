import uuid
from collections.abc import Callable, Coroutine
from typing import Annotated, Any, Literal

from fastapi import Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.errors import (  # re-exported: routers and services import these
    ACCOUNT_DISABLED,
    SESSION_EXPIRED,
    SESSION_INVALID,
    SIGN_IN_REQUIRED,
)
from app.core.currency import (
    DEFAULT_DISPLAY_CURRENCY,
    CurrencyConverter,
    supported_display_currencies,
)
from app.core.security import TokenExpiredError, decode_token
from app.models.user import User, UserRole
from app.services.exchange_rate_service import (
    ExchangeRateService,
    get_exchange_rate_service,
)
from app.services.user_service import UserService, get_user_service

SUPPORTED_LOCALES: tuple[str, ...] = ("uz", "ru", "en")
DEFAULT_LOCALE = "en"

Locale = Literal["uz", "ru", "en"]


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


class _Bearer(HTTPBearer):
    """HTTPBearer whose "no token" message reads like the rest of the API.

    FastAPI's own wording is the bare "Not authenticated", and the frontend
    prints ``detail`` to the guest unchanged.
    """

    async def __call__(self, request: Request) -> HTTPAuthorizationCredentials | None:
        try:
            return await super().__call__(request)
        except HTTPException as exc:
            if exc.status_code == status.HTTP_401_UNAUTHORIZED:
                raise _unauthorized(SIGN_IN_REQUIRED) from exc
            raise


bearer_scheme = _Bearer(auto_error=True)
optional_bearer_scheme = _Bearer(auto_error=False)


def _resolve_user_id(credentials: HTTPAuthorizationCredentials) -> uuid.UUID:
    """The user id inside an access token, or 401 explaining what to do next.

    An expired token is called out separately: it is the one case where the
    guest did nothing wrong and signing in again fixes it.
    """

    try:
        claims = decode_token(credentials.credentials)
    except TokenExpiredError as exc:
        raise _unauthorized(SESSION_EXPIRED) from exc
    except ValueError as exc:
        raise _unauthorized(SESSION_INVALID) from exc
    if claims.get("type") != "access":
        # A refresh token sent where an access token belongs.
        raise _unauthorized(SESSION_INVALID)
    try:
        return uuid.UUID(claims["sub"])
    except (KeyError, ValueError) as exc:
        raise _unauthorized(SESSION_INVALID) from exc


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    users: Annotated[UserService, Depends(get_user_service)],
) -> User:
    user_id = _resolve_user_id(credentials)
    user = await users.get_by_id(user_id)
    if user is None:
        raise _unauthorized(SESSION_INVALID)
    if not user.is_active:
        raise _unauthorized(ACCOUNT_DISABLED)
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
    if user is None:
        raise _unauthorized(SESSION_INVALID)
    if not user.is_active:
        raise _unauthorized(ACCOUNT_DISABLED)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_optional_user)]


def _parse_accept_language(header: str) -> str | None:
    best_locale: str | None = None
    best_q = -1.0
    best_index = len(header)

    for index, part in enumerate(header.split(",")):
        pieces = [piece.strip() for piece in part.split(";")]
        tag = pieces[0].lower()
        q = _accept_language_q(pieces[1:])
        if q <= 0:
            continue
        primary = tag.split("-", 1)[0]
        if primary in SUPPORTED_LOCALES and (
            q > best_q or (q == best_q and index < best_index)
        ):
            best_locale = primary
            best_q = q
            best_index = index
    return best_locale


def _accept_language_q(params: list[str]) -> float:
    for param in params:
        key, separator, value = param.partition("=")
        if key.strip().lower() != "q" or separator != "=":
            continue
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 1.0


def get_locale(
    lang: Annotated[str | None, Query(description="Locale (uz, ru, en)")] = None,
    accept_language: Annotated[str | None, Header()] = None,
) -> Locale:
    if lang:
        candidate = _as_locale(lang.strip().lower())
        if candidate is not None:
            return candidate
    if accept_language:
        resolved = _as_locale(_parse_accept_language(accept_language))
        if resolved is not None:
            return resolved
    return DEFAULT_LOCALE


def _as_locale(value: str | None) -> Locale | None:
    if value == "uz":
        return "uz"
    if value == "ru":
        return "ru"
    if value == "en":
        return "en"
    return None


def get_include_translations(
    include_translations: Annotated[
        bool,
        Query(description="Return full {uz,ru,en} dicts instead of resolved strings"),
    ] = False,
) -> bool:
    return include_translations


def get_currency(
    currency: Annotated[
        str | None,
        Query(
            description=(
                "Display currency (UZS, USD, EUR, RUB, KZT). All prices gain "
                "display_price/display_currency fields converted to it. "
                "Unknown values fall back to UZS."
            )
        ),
    ] = None,
    x_currency: Annotated[str | None, Header()] = None,
) -> str:
    supported = supported_display_currencies()
    for raw in (currency, x_currency):
        if raw is None:
            continue
        candidate = raw.strip().upper()
        if candidate in supported:
            return candidate
    return DEFAULT_DISPLAY_CURRENCY


async def get_currency_converter(
    currency: Annotated[str, Depends(get_currency)],
    rates: Annotated[ExchangeRateService, Depends(get_exchange_rate_service)],
) -> CurrencyConverter:
    return await rates.get_converter(currency)


# Shared, anonymous responses that change only when an admin edits content: a
# few minutes of CDN/browser caching takes them off the homepage's critical path.
PUBLIC_CACHE_CONTROL = "public, max-age=300, stale-while-revalidate=600"


def public_cache(response: Response) -> None:
    """Mark a GET as cacheable by anyone. Never use it on per-user data.

    The body depends on the request language and display currency, which also
    arrive as headers, so caches must key on those too.
    """
    response.headers["Cache-Control"] = PUBLIC_CACHE_CONTROL
    response.headers["Vary"] = "Accept-Language, X-Currency"


LocaleDep = Annotated[Locale, Depends(get_locale)]
IncludeTranslationsDep = Annotated[bool, Depends(get_include_translations)]
CurrencyDep = Annotated[str, Depends(get_currency)]
ConverterDep = Annotated[CurrencyConverter, Depends(get_currency_converter)]


def not_found(detail: str = "Not found") -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


# What each role is called in a sentence a guest or a hotel manager can read.
ROLE_LABELS: dict[UserRole, str] = {
    UserRole.SUPER_ADMIN: "a platform administrator",
    UserRole.ADMIN: "a property administrator",
    UserRole.AGENT: "a B2B agent",
    UserRole.TRANSFER_ADMIN: "the transfer operator",
    UserRole.CUSTOMER: "a customer",
}


def describe_roles(roles: set[UserRole]) -> str:
    """``{ADMIN, SUPER_ADMIN}`` → "a property administrator or a platform administrator"."""

    labels = [ROLE_LABELS[role] for role in UserRole if role in roles]
    if not labels:
        return "another account type"
    if len(labels) == 1:
        return labels[0]
    return f"{', '.join(labels[:-1])} or {labels[-1]}"


def require_roles(
    *roles: UserRole,
    detail: str | None = None,
) -> Callable[[User], Coroutine[Any, Any, User]]:
    """Gate an endpoint on the caller's role.

    The default 403 names the role that would work, because the frontend shows
    ``detail`` verbatim and "Insufficient permissions" leaves the operator
    guessing which of their logins to use.
    """

    allowed = set(roles)
    message = detail or (
        f"This action is only available to {describe_roles(allowed)}. "
        "Sign in with an account that has that role."
    )

    async def _checker(user: CurrentUser) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=message,
            )
        return user

    return _checker


def is_admin_or_above(user: User | None) -> bool:
    return user is not None and user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN)


def is_super_admin(user: User | None) -> bool:
    return user is not None and user.role == UserRole.SUPER_ADMIN
