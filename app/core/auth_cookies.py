"""HttpOnly refresh-token cookie helpers.

Access tokens stay in the JSON body and travel via ``Authorization: Bearer``.
Refresh tokens never touch JavaScript — they live in this cookie only, scoped
to ``/api/auth`` so browsers only attach them to login/refresh/logout.
"""

from fastapi import Response

from app.core.config import settings

REFRESH_COOKIE_NAME = "refresh_token"
REFRESH_COOKIE_PATH = "/api/auth"


def set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=settings.ENVIRONMENT != "local",
        samesite="lax",
    )


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=settings.ENVIRONMENT != "local",
        samesite="lax",
    )
