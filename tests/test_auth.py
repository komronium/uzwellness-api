from httpx import AsyncClient


async def test_register_creates_customer(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/auth/register",
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
    first = await client.post("/api/auth/register", json=payload)
    assert first.status_code == 201

    second = await client.post("/api/auth/register", json=payload)
    assert second.status_code == 409


async def test_register_short_password_returns_422(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/auth/register",
        json={"email": "weak@test.com", "password": "short"},
    )
    assert resp.status_code == 422


async def test_register_invalid_email_returns_422(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/auth/register",
        json={"email": "not-an-email", "password": "validpass123"},
    )
    assert resp.status_code == 422


async def test_login_returns_token_pair(client: AsyncClient, customer_user) -> None:
    resp = await client.post(
        "/api/auth/login",
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
        "/api/auth/login",
        json={"email": customer_user.email, "password": "wrongpass123"},
    )
    assert resp.status_code == 401


async def test_login_unknown_user_returns_401(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/auth/login",
        json={"email": "ghost@test.com", "password": "anything123"},
    )
    assert resp.status_code == 401


async def test_refresh_returns_new_pair(client: AsyncClient, customer_user) -> None:
    login = await client.post(
        "/api/auth/login",
        json={"email": customer_user.email, "password": "customerpass123"},
    )
    refresh_token = login.json()["refresh_token"]

    resp = await client.post(
        "/api/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert resp.status_code == 200
    assert resp.json()["access_token"]


async def test_refresh_with_access_token_returns_401(
    client: AsyncClient, customer_user
) -> None:
    login = await client.post(
        "/api/auth/login",
        json={"email": customer_user.email, "password": "customerpass123"},
    )
    access_token = login.json()["access_token"]

    resp = await client.post(
        "/api/auth/refresh",
        json={"refresh_token": access_token},
    )
    assert resp.status_code == 401


async def test_refresh_with_garbage_returns_401(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/auth/refresh",
        json={"refresh_token": "not-a-real-token"},
    )
    assert resp.status_code == 401


# ---------- logout ----------


async def test_logout_revokes_refresh_token(client: AsyncClient, customer_user) -> None:
    login = await client.post(
        "/api/auth/login",
        json={"email": customer_user.email, "password": "customerpass123"},
    )
    refresh_token = login.json()["refresh_token"]
    resp = await client.post("/api/auth/logout", json={"refresh_token": refresh_token})
    assert resp.status_code == 204
    # Using the now-revoked token must fail
    second = await client.post(
        "/api/auth/refresh", json={"refresh_token": refresh_token}
    )
    assert second.status_code == 401


async def test_logout_all_revokes_every_session(
    client: AsyncClient, customer_user, customer_headers
) -> None:
    a = await client.post(
        "/api/auth/login",
        json={"email": customer_user.email, "password": "customerpass123"},
    )
    b = await client.post(
        "/api/auth/login",
        json={"email": customer_user.email, "password": "customerpass123"},
    )
    resp = await client.post("/api/auth/logout-all", headers=customer_headers)
    assert resp.status_code == 204
    for r in (a, b):
        rt = r.json()["refresh_token"]
        refr = await client.post("/api/auth/refresh", json={"refresh_token": rt})
        assert refr.status_code == 401


# ---------- change-password ----------


async def test_change_password_success(
    client: AsyncClient, customer_user, customer_headers
) -> None:
    resp = await client.post(
        "/api/auth/change-password",
        headers=customer_headers,
        json={
            "current_password": "customerpass123",
            "new_password": "brandnewpass99",
            "confirm_new_password": "brandnewpass99",
        },
    )
    assert resp.status_code == 204
    # Old password no longer works
    old = await client.post(
        "/api/auth/login",
        json={"email": customer_user.email, "password": "customerpass123"},
    )
    assert old.status_code == 401
    # New password works
    new = await client.post(
        "/api/auth/login",
        json={"email": customer_user.email, "password": "brandnewpass99"},
    )
    assert new.status_code == 200


async def test_change_password_wrong_current_returns_401(
    client: AsyncClient, customer_headers
) -> None:
    resp = await client.post(
        "/api/auth/change-password",
        headers=customer_headers,
        json={
            "current_password": "wrongoldpass",
            "new_password": "brandnewpass99",
            "confirm_new_password": "brandnewpass99",
        },
    )
    assert resp.status_code == 401


async def test_change_password_mismatch_confirm_returns_422(
    client: AsyncClient, customer_headers
) -> None:
    resp = await client.post(
        "/api/auth/change-password",
        headers=customer_headers,
        json={
            "current_password": "customerpass123",
            "new_password": "brandnewpass99",
            "confirm_new_password": "different99",
        },
    )
    assert resp.status_code == 422


async def test_change_password_same_as_current_returns_422(
    client: AsyncClient, customer_headers
) -> None:
    resp = await client.post(
        "/api/auth/change-password",
        headers=customer_headers,
        json={
            "current_password": "customerpass123",
            "new_password": "customerpass123",
            "confirm_new_password": "customerpass123",
        },
    )
    assert resp.status_code == 422


async def test_change_password_short_returns_422(
    client: AsyncClient, customer_headers
) -> None:
    resp = await client.post(
        "/api/auth/change-password",
        headers=customer_headers,
        json={
            "current_password": "customerpass123",
            "new_password": "short",
            "confirm_new_password": "short",
        },
    )
    assert resp.status_code == 422


async def test_change_password_revokes_other_sessions(
    client: AsyncClient, customer_user, customer_headers
) -> None:
    # Login twice to have a stale refresh token
    other = await client.post(
        "/api/auth/login",
        json={"email": customer_user.email, "password": "customerpass123"},
    )
    other_refresh = other.json()["refresh_token"]

    change = await client.post(
        "/api/auth/change-password",
        headers=customer_headers,
        json={
            "current_password": "customerpass123",
            "new_password": "brandnewpass99",
            "confirm_new_password": "brandnewpass99",
        },
    )
    assert change.status_code == 204

    # The other session's refresh token should now be invalid
    refr = await client.post("/api/auth/refresh", json={"refresh_token": other_refresh})
    assert refr.status_code == 401


async def test_change_password_anonymous_returns_401(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/auth/change-password",
        json={
            "current_password": "x" * 8,
            "new_password": "y" * 8,
            "confirm_new_password": "y" * 8,
        },
    )
    assert resp.status_code == 401
