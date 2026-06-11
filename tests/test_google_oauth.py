"""Google OAuth login flow (Google's endpoints are monkeypatched)."""

from urllib.parse import parse_qs, urlparse

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.user import User, UserRole
from app.services import google_oauth
from tests.factories import make_user

GOOGLE_PROFILE = {
    "sub": "108943571",
    "email": "Gulnora@gmail.com",
    "email_verified": True,
    "name": "Gulnora Karimova",
}


@pytest.fixture
def google_configured(monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "test-secret")
    monkeypatch.setattr(
        settings, "GOOGLE_REDIRECT_URI", "http://test/api/auth/google/callback"
    )
    monkeypatch.setattr(
        settings, "OAUTH_FRONTEND_REDIRECT_URL", "http://front/auth/callback"
    )


@pytest.fixture
def fake_google(google_configured, monkeypatch):
    async def _exchange(code: str) -> dict:
        assert code == "good-code"
        return {"access_token": "google-access-token"}

    async def _userinfo(access_token: str) -> dict:
        assert access_token == "google-access-token"
        return dict(GOOGLE_PROFILE)

    monkeypatch.setattr("app.api.routers.auth.google_oauth.exchange_code", _exchange)
    monkeypatch.setattr("app.api.routers.auth.google_oauth.fetch_userinfo", _userinfo)


async def _start_flow(client: AsyncClient) -> str:
    """Hit /auth/google; return the state Google would echo back."""
    resp = await client.get("/api/auth/google")
    assert resp.status_code == 307
    location = resp.headers["location"]
    assert location.startswith(google_oauth.GOOGLE_AUTH_URL)
    params = parse_qs(urlparse(location).query)
    assert params["client_id"] == ["test-client-id"]
    assert params["scope"] == ["openid email profile"]
    state = params["state"][0]
    # state is also pinned in a cookie for the callback
    assert client.cookies.get(google_oauth.STATE_COOKIE) == state
    return state


async def test_google_login_not_configured_returns_503(client: AsyncClient):
    resp = await client.get("/api/auth/google")
    assert resp.status_code == 503
    resp = await client.get("/api/auth/google/callback")
    assert resp.status_code == 503


async def test_google_flow_creates_customer(
    client: AsyncClient, db: AsyncSession, fake_google
):
    state = await _start_flow(client)
    resp = await client.get(
        "/api/auth/google/callback", params={"code": "good-code", "state": state}
    )
    assert resp.status_code == 307
    location = resp.headers["location"]
    assert location.startswith("http://front/auth/callback#")
    fragment = parse_qs(urlparse(location).fragment)
    assert fragment["access_token"][0]
    assert fragment["refresh_token"][0]

    user = (
        await db.execute(select(User).where(User.email == "gulnora@gmail.com"))
    ).scalar_one()
    assert user.role == UserRole.CUSTOMER
    assert user.full_name == "Gulnora Karimova"


async def test_google_flow_logs_in_existing_user(
    client: AsyncClient, db: AsyncSession, fake_google
):
    existing = await make_user(db, email="gulnora@gmail.com")
    state = await _start_flow(client)
    resp = await client.get(
        "/api/auth/google/callback", params={"code": "good-code", "state": state}
    )
    assert resp.status_code == 307
    assert "access_token=" in resp.headers["location"]

    users = (
        (await db.execute(select(User).where(User.email == "gulnora@gmail.com")))
        .scalars()
        .all()
    )
    assert len(users) == 1
    assert users[0].id == existing.id


async def test_callback_rejects_forged_state(client: AsyncClient, fake_google):
    await _start_flow(client)
    resp = await client.get(
        "/api/auth/google/callback",
        params={"code": "good-code", "state": "forged-state"},
    )
    assert resp.status_code == 307
    assert "error=google_invalid_state" in resp.headers["location"]


async def test_callback_without_cookie_rejected(client: AsyncClient, fake_google):
    state = await _start_flow(client)
    client.cookies.delete(google_oauth.STATE_COOKIE)
    resp = await client.get(
        "/api/auth/google/callback", params={"code": "good-code", "state": state}
    )
    assert resp.status_code == 307
    assert "error=google_invalid_state" in resp.headers["location"]


async def test_callback_user_cancelled(client: AsyncClient, google_configured):
    resp = await client.get(
        "/api/auth/google/callback", params={"error": "access_denied"}
    )
    assert resp.status_code == 307
    assert "error=google_access_denied" in resp.headers["location"]


async def test_unverified_email_rejected(
    client: AsyncClient, google_configured, monkeypatch
):
    async def _exchange(code: str) -> dict:
        return {"access_token": "google-access-token"}

    async def _userinfo(access_token: str) -> dict:
        return {**GOOGLE_PROFILE, "email_verified": False}

    monkeypatch.setattr("app.api.routers.auth.google_oauth.exchange_code", _exchange)
    monkeypatch.setattr("app.api.routers.auth.google_oauth.fetch_userinfo", _userinfo)

    state = await _start_flow(client)
    resp = await client.get(
        "/api/auth/google/callback", params={"code": "good-code", "state": state}
    )
    assert resp.status_code == 307
    assert "error=google_account_rejected" in resp.headers["location"]


async def test_inactive_user_rejected(
    client: AsyncClient, db: AsyncSession, fake_google
):
    await make_user(db, email="gulnora@gmail.com", is_active=False)
    state = await _start_flow(client)
    resp = await client.get(
        "/api/auth/google/callback", params={"code": "good-code", "state": state}
    )
    assert resp.status_code == 307
    assert "error=google_account_rejected" in resp.headers["location"]
