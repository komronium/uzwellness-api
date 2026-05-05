from httpx import AsyncClient


async def test_register_creates_customer(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "new@test.com",
            "password": "validpass123",
            "full_name": "New User",
            "phone": "+998900000000",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "new@test.com"
    assert body["role"] == "customer"
    assert body["is_active"] is True
    assert "id" in body


async def test_register_duplicate_email_returns_409(client: AsyncClient) -> None:
    payload = {"email": "dup@test.com", "password": "validpass123"}
    first = await client.post("/api/v1/auth/register", json=payload)
    assert first.status_code == 201

    second = await client.post("/api/v1/auth/register", json=payload)
    assert second.status_code == 409


async def test_register_short_password_returns_422(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "weak@test.com", "password": "short"},
    )
    assert resp.status_code == 422


async def test_register_invalid_email_returns_422(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "password": "validpass123"},
    )
    assert resp.status_code == 422


async def test_login_returns_token_pair(client: AsyncClient, customer_user) -> None:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": customer_user.email, "password": "customerpass123"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["access_token"] != body["refresh_token"]


async def test_login_wrong_password_returns_401(
    client: AsyncClient, customer_user
) -> None:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": customer_user.email, "password": "wrongpass123"},
    )
    assert resp.status_code == 401


async def test_login_unknown_user_returns_401(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "ghost@test.com", "password": "anything123"},
    )
    assert resp.status_code == 401


async def test_refresh_returns_new_pair(client: AsyncClient, customer_user) -> None:
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": customer_user.email, "password": "customerpass123"},
    )
    refresh_token = login.json()["refresh_token"]

    resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert resp.status_code == 200
    assert resp.json()["access_token"]


async def test_refresh_with_access_token_returns_401(
    client: AsyncClient, customer_user
) -> None:
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": customer_user.email, "password": "customerpass123"},
    )
    access_token = login.json()["access_token"]

    resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": access_token},
    )
    assert resp.status_code == 401


async def test_refresh_with_garbage_returns_401(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "not-a-real-token"},
    )
    assert resp.status_code == 401
