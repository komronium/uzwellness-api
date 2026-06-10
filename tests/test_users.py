import uuid

from httpx import AsyncClient


async def test_me_without_token_returns_401(client: AsyncClient) -> None:
    resp = await client.get("/api/users/me")
    assert resp.status_code == 401


async def test_me_returns_current_user(
    client: AsyncClient, customer_user, customer_headers
) -> None:
    resp = await client.get("/api/users/me", headers=customer_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == customer_user.email
    assert body["role"] == "customer"
    assert body["id"] == str(customer_user.id)


async def test_me_with_garbage_token_returns_401(client: AsyncClient) -> None:
    resp = await client.get(
        "/api/users/me", headers={"Authorization": "Bearer not-a-token"}
    )
    assert resp.status_code == 401


async def test_list_users_as_customer_returns_403(
    client: AsyncClient, customer_headers
) -> None:
    resp = await client.get("/api/users", headers=customer_headers)
    assert resp.status_code == 403


async def test_list_users_as_admin_returns_403(
    client: AsyncClient, admin_headers
) -> None:
    resp = await client.get("/api/users", headers=admin_headers)
    assert resp.status_code == 403


async def test_list_users_as_super_admin_returns_all(
    client: AsyncClient,
    super_admin_headers,
    customer_user,
    admin_user,
    super_admin_user,
) -> None:
    resp = await client.get("/api/users", headers=super_admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 3
    emails = {u["email"] for u in body["items"]}
    assert emails == {customer_user.email, admin_user.email, super_admin_user.email}


async def test_list_users_filter_by_role(
    client: AsyncClient,
    super_admin_headers,
    customer_user,
    admin_user,
    super_admin_user,
) -> None:
    resp = await client.get("/api/users?role=customer", headers=super_admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["email"] == customer_user.email


async def test_list_users_pagination(
    client: AsyncClient,
    super_admin_headers,
    customer_user,
    admin_user,
    super_admin_user,
) -> None:
    resp = await client.get("/api/users?limit=2&offset=0", headers=super_admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert body["limit"] == 2
    assert body["offset"] == 0


async def test_get_user_by_id_as_super_admin(
    client: AsyncClient, super_admin_headers, customer_user
) -> None:
    resp = await client.get(
        f"/api/users/{customer_user.id}", headers=super_admin_headers
    )
    assert resp.status_code == 200
    assert resp.json()["email"] == customer_user.email


async def test_get_user_by_id_not_found(
    client: AsyncClient, super_admin_headers
) -> None:
    fake_id = uuid.uuid4()
    resp = await client.get(f"/api/users/{fake_id}", headers=super_admin_headers)
    assert resp.status_code == 404


async def test_get_user_by_id_as_customer_returns_403(
    client: AsyncClient, customer_headers, admin_user
) -> None:
    resp = await client.get(f"/api/users/{admin_user.id}", headers=customer_headers)
    assert resp.status_code == 403


async def test_patch_user_role_as_super_admin(
    client: AsyncClient, super_admin_headers, customer_user
) -> None:
    resp = await client.patch(
        f"/api/users/{customer_user.id}",
        headers=super_admin_headers,
        json={"role": "agent"},
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "agent"


async def test_patch_user_deactivate(
    client: AsyncClient, super_admin_headers, customer_user
) -> None:
    resp = await client.patch(
        f"/api/users/{customer_user.id}",
        headers=super_admin_headers,
        json={"is_active": False},
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False


async def test_deactivated_user_cannot_authenticate(
    client: AsyncClient, super_admin_headers, customer_user
) -> None:
    await client.patch(
        f"/api/users/{customer_user.id}",
        headers=super_admin_headers,
        json={"is_active": False},
    )
    resp = await client.post(
        "/api/auth/login",
        json={"email": customer_user.email, "password": "customerpass123"},
    )
    assert resp.status_code == 401


async def test_patch_user_as_customer_returns_403(
    client: AsyncClient, customer_headers, admin_user
) -> None:
    resp = await client.patch(
        f"/api/users/{admin_user.id}",
        headers=customer_headers,
        json={"role": "super_admin"},
    )
    assert resp.status_code == 403


async def test_patch_unknown_user_returns_404(
    client: AsyncClient, super_admin_headers
) -> None:
    fake_id = uuid.uuid4()
    resp = await client.patch(
        f"/api/users/{fake_id}",
        headers=super_admin_headers,
        json={"is_active": False},
    )
    assert resp.status_code == 404


async def test_customer_patches_own_profile(
    client: AsyncClient, customer_headers, customer_user
) -> None:
    resp = await client.patch(
        f"/api/users/{customer_user.id}",
        headers=customer_headers,
        json={
            "full_name": "New Name",
            "phone": "+998901234567",
            "email": "new-email@example.com",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["full_name"] == "New Name"
    assert body["phone"] == "+998901234567"
    assert body["email"] == "new-email@example.com"
    assert body["role"] == "customer"


async def test_customer_cannot_patch_own_role(
    client: AsyncClient, customer_headers, customer_user
) -> None:
    resp = await client.patch(
        f"/api/users/{customer_user.id}",
        headers=customer_headers,
        json={"role": "super_admin"},
    )
    assert resp.status_code == 403


async def test_customer_cannot_patch_own_is_active(
    client: AsyncClient, customer_headers, customer_user
) -> None:
    resp = await client.patch(
        f"/api/users/{customer_user.id}",
        headers=customer_headers,
        json={"is_active": False, "full_name": "Sneaky"},
    )
    assert resp.status_code == 403


async def test_customer_cannot_patch_other_user_profile(
    client: AsyncClient, customer_headers, admin_user
) -> None:
    resp = await client.patch(
        f"/api/users/{admin_user.id}",
        headers=customer_headers,
        json={"full_name": "Hijacked"},
    )
    assert resp.status_code == 403


async def test_self_patch_email_conflict_returns_409(
    client: AsyncClient, customer_headers, customer_user, admin_user
) -> None:
    resp = await client.patch(
        f"/api/users/{customer_user.id}",
        headers=customer_headers,
        json={"email": admin_user.email},
    )
    assert resp.status_code == 409


async def test_self_patch_email_then_login_with_new_email(
    client: AsyncClient, customer_headers, customer_user
) -> None:
    resp = await client.patch(
        f"/api/users/{customer_user.id}",
        headers=customer_headers,
        json={"email": "Renamed@Example.com"},
    )
    assert resp.status_code == 200
    assert resp.json()["email"] == "renamed@example.com"
    login = await client.post(
        "/api/auth/login",
        json={"email": "renamed@example.com", "password": "customerpass123"},
    )
    assert login.status_code == 200
