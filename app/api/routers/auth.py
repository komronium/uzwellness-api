import logging

import httpx
from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Response, status
from fastapi.responses import RedirectResponse

from app.api.deps import CurrentUser
from app.api.rate_limits import login_rate_limit, register_rate_limit
from app.core.auth_cookies import (
    REFRESH_COOKIE_NAME,
    clear_refresh_cookie,
    set_refresh_cookie,
)
from app.core.config import settings
from app.core.errors import SIGN_IN_REQUIRED
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    Token,
)
from app.schemas.user import UserCreate, UserRead
from app.services import google_oauth
from app.services.auth_service import AuthService, get_auth_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Identity"])


def _token_response(response: Response, access_token: str, refresh_token: str) -> Token:
    set_refresh_cookie(response, refresh_token)
    return Token(access_token=access_token)


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(register_rate_limit)],
)
async def register(
    payload: UserCreate,
    auth: AuthService = Depends(get_auth_service),
) -> UserRead:
    user = await auth.register(payload)
    return UserRead.model_validate(user)


@router.post(
    "/login",
    response_model=Token,
    dependencies=[Depends(login_rate_limit)],
)
async def login(
    payload: LoginRequest,
    response: Response,
    auth: AuthService = Depends(get_auth_service),
) -> Token:
    issued = await auth.login(payload.email, payload.password)
    return _token_response(response, issued.access_token, issued.refresh_token)


@router.get("/google", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
async def google_login() -> RedirectResponse:
    """Send the browser to Google's consent screen."""
    if not google_oauth.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Signing in with Google is not available on this site. "
                "Please use your email and password."
            ),
        )
    state = google_oauth.make_state()
    response = RedirectResponse(google_oauth.build_authorization_url(state))
    # Lax cookies are sent on the top-level GET navigation back from Google,
    # binding the callback to the browser that started the flow.
    response.set_cookie(
        google_oauth.STATE_COOKIE,
        state,
        max_age=google_oauth.STATE_TTL_MINUTES * 60,
        httponly=True,
        secure=settings.ENVIRONMENT != "local",
        samesite="lax",
    )
    return response


def _frontend_redirect(fragment: str) -> RedirectResponse:
    response = RedirectResponse(f"{settings.OAUTH_FRONTEND_REDIRECT_URL}#{fragment}")
    response.delete_cookie(google_oauth.STATE_COOKIE)
    return response


@router.get("/google/callback", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
async def google_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    state_cookie: str | None = Cookie(default=None, alias=google_oauth.STATE_COOKIE),
    auth: AuthService = Depends(get_auth_service),
) -> RedirectResponse:
    """Exchange Google's code and hand the access token to the frontend.

    The refresh token is set as an HttpOnly cookie on this response — it never
    appears in the URL fragment (which JavaScript can read).
    """
    if not google_oauth.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Signing in with Google is not available on this site. "
                "Please use your email and password."
            ),
        )
    if error:  # user cancelled the consent screen
        return _frontend_redirect("error=google_access_denied")
    if (
        not code
        or not state
        or state != state_cookie
        or not google_oauth.is_valid_state(state)
    ):
        return _frontend_redirect("error=google_invalid_state")
    try:
        tokens = await google_oauth.exchange_code(code)
        userinfo = await google_oauth.fetch_userinfo(tokens["access_token"])
    except (httpx.HTTPError, KeyError):
        logger.exception("Google OAuth code exchange failed")
        return _frontend_redirect("error=google_auth_failed")
    try:
        issued = await auth.login_with_google(userinfo)
    except HTTPException:
        return _frontend_redirect("error=google_account_rejected")
    response = _frontend_redirect(f"access_token={issued.access_token}")
    set_refresh_cookie(response, issued.refresh_token)
    return response


@router.post("/refresh", response_model=Token)
async def refresh(
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE_NAME),
    auth: AuthService = Depends(get_auth_service),
) -> Token:
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=SIGN_IN_REQUIRED,
        )
    issued = await auth.refresh(refresh_token)
    return _token_response(response, issued.access_token, issued.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE_NAME),
    auth: AuthService = Depends(get_auth_service),
) -> None:
    if refresh_token:
        await auth.logout(refresh_token)
    clear_refresh_cookie(response)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(
    response: Response,
    current_user: CurrentUser,
    auth: AuthService = Depends(get_auth_service),
) -> None:
    await auth.logout_all(current_user)
    clear_refresh_cookie(response)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    payload: ChangePasswordRequest,
    response: Response,
    current_user: CurrentUser,
    auth: AuthService = Depends(get_auth_service),
) -> None:
    await auth.change_password(
        current_user, payload.current_password, payload.new_password
    )
    # All refresh tokens were revoked — drop the browser cookie so the next
    # /auth/refresh does not present a dead session.
    clear_refresh_cookie(response)
