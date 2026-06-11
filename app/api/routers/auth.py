import logging

import httpx
from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse

from app.api.deps import CurrentUser
from app.api.rate_limits import login_rate_limit, register_rate_limit
from app.core.config import settings
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    RefreshRequest,
    Token,
)
from app.schemas.user import UserCreate, UserRead
from app.services import google_oauth
from app.services.auth_service import AuthService, get_auth_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Identity"])


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
    auth: AuthService = Depends(get_auth_service),
) -> Token:
    return await auth.login(payload.email, payload.password)


@router.get("/google", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
async def google_login() -> RedirectResponse:
    """Send the browser to Google's consent screen."""
    if not google_oauth.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth is not configured",
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
    """Exchange Google's code and hand tokens to the frontend via fragment."""
    if not google_oauth.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth is not configured",
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
        token = await auth.login_with_google(userinfo)
    except HTTPException:
        return _frontend_redirect("error=google_account_rejected")
    return _frontend_redirect(
        f"access_token={token.access_token}&refresh_token={token.refresh_token}"
    )


@router.post("/refresh", response_model=Token)
async def refresh(
    payload: RefreshRequest,
    auth: AuthService = Depends(get_auth_service),
) -> Token:
    return await auth.refresh(payload.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    payload: RefreshRequest,
    auth: AuthService = Depends(get_auth_service),
) -> None:
    await auth.logout(payload.refresh_token)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(
    current_user: CurrentUser,
    auth: AuthService = Depends(get_auth_service),
) -> None:
    await auth.logout_all(current_user)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    payload: ChangePasswordRequest,
    current_user: CurrentUser,
    auth: AuthService = Depends(get_auth_service),
) -> None:
    await auth.change_password(
        current_user, payload.current_password, payload.new_password
    )
