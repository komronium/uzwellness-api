"""Google OAuth 2.0 (authorization-code flow, server-side).

The frontend sends the browser to ``GET /auth/google``; we redirect to
Google's consent screen with a signed ``state`` (also pinned in a short-lived
cookie). Google calls ``GET /auth/google/callback``, we exchange the code,
read the verified profile and hand our own JWT pair back to the frontend via
the URL fragment (fragments never reach server logs).
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from jose import jwt

from app.core.config import settings

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"  # nosec B105
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"

STATE_COOKIE = "g_oauth_state"
STATE_TTL_MINUTES = 10


def is_configured() -> bool:
    return bool(
        settings.GOOGLE_CLIENT_ID
        and settings.GOOGLE_CLIENT_SECRET
        and settings.GOOGLE_REDIRECT_URI
    )


def make_state() -> str:
    now = datetime.now(UTC)
    payload = {
        "type": "oauth_state",
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + timedelta(minutes=STATE_TTL_MINUTES),
    }
    return jwt.encode(
        payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )


def is_valid_state(state: str) -> bool:
    try:
        claims = jwt.decode(
            state, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
    except Exception:
        return False
    return claims.get("type") == "oauth_state"


def build_authorization_url(state: str) -> str:
    params = httpx.QueryParams(
        client_id=settings.GOOGLE_CLIENT_ID,
        redirect_uri=settings.GOOGLE_REDIRECT_URI,
        response_type="code",
        scope="openid email profile",
        state=state,
        access_type="online",
        prompt="select_account",
    )
    return f"{GOOGLE_AUTH_URL}?{params}"


async def exchange_code(code: str) -> dict[str, Any]:
    """Trade the authorization code for Google tokens."""
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
                "code": code,
            },
        )
        resp.raise_for_status()
        return resp.json()


async def fetch_userinfo(access_token: str) -> dict[str, Any]:
    """Profile from Google's OpenID userinfo endpoint: sub, email,
    email_verified, name, picture."""
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        return resp.json()
