import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sanatorium import SanatoriumStatus
from app.models.user import UserRole
from tests.factories import make_sanatorium, make_user

# ---------- helpers ----------


async def _login(client: AsyncClient, email: str, password: str) -> dict[str, str]:
    resp = await client.post(
        "/api/auth/login", json={"email": email, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


CREATE_PAYLOAD = {
    "name": {"uz": "Vodiy Shifosi", "en": "Valley Healing"},
    "description": {"uz": "Eng yaxshi", "en": "The best"},
    "city": "Toshkent",
    "address": "Amir Temur 12",
    "stars": 4,
}


# ---------- create ----------


async def test_create_as_super_admin_works(
    client: AsyncClient, super_admin_headers
) -> None:
    resp = await client.post(
        "/api/sanatoriums", json=CREATE_PAYLOAD, headers=super_admin_headers
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"]["uz"] == "Vodiy Shifosi"
    assert body["name"]["en"] == "Valley Healing"
    assert body["slug"] == "vodiy-shifosi"
    assert body["status"] == "pending"
    assert body["description"]["uz"] == "Eng yaxshi"
    assert body["description"]["en"] == "The best"
    assert body["description"]["ru"] is None


async def test_create_as_admin_auto_assigns_owner(
    client: AsyncClient, admin_headers, admin_user
) -> None:
    resp = await client.post(
        "/api/sanatoriums", json=CREATE_PAYLOAD, headers=admin_headers
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["admin_user_id"] == str(admin_user.id)


async def test_create_as_customer_returns_403(
    client: AsyncClient, customer_headers
) -> None:
    resp = await client.post(
        "/api/sanatoriums", json=CREATE_PAYLOAD, headers=customer_headers
    )
    assert resp.status_code == 403


async def test_create_anonymous_returns_401(client: AsyncClient) -> None:
    resp = await client.post("/api/sanatoriums", json=CREATE_PAYLOAD)
    assert resp.status_code == 401


async def test_create_slug_collision_suffixes(
    client: AsyncClient, super_admin_headers
) -> None:
    first = await client.post(
        "/api/sanatoriums", json=CREATE_PAYLOAD, headers=super_admin_headers
    )
    second = await client.post(
        "/api/sanatoriums",
        json={**CREATE_PAYLOAD, "address": "Other 2"},
        headers=super_admin_headers,
    )
    assert first.json()["slug"] == "vodiy-shifosi"
    assert second.json()["slug"] == "vodiy-shifosi-2"


async def test_create_invalid_stars_returns_422(
    client: AsyncClient, super_admin_headers
) -> None:
    resp = await client.post(
        "/api/sanatoriums",
        json={**CREATE_PAYLOAD, "stars": 99},
        headers=super_admin_headers,
    )
    assert resp.status_code == 422


# ---------- patch ----------


async def test_patch_as_super_admin(
    client: AsyncClient, db: AsyncSession, super_admin_headers
) -> None:
    sanatorium = await make_sanatorium(db, name="Old Name", slug="old-name")
    resp = await client.patch(
        f"/api/sanatoriums/{sanatorium.id}",
        json={"name": {"uz": "New Name"}, "stars": 5},
        headers=super_admin_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"]["uz"] == "New Name"
    assert body["slug"] == "new-name"  # auto-regenerated
    assert body["stars"] == 5


async def test_patch_as_owning_admin(
    client: AsyncClient, db: AsyncSession, admin_user, admin_headers
) -> None:
    sanatorium = await make_sanatorium(
        db, name="Owned", slug="owned", admin_user_id=admin_user.id
    )
    resp = await client.patch(
        f"/api/sanatoriums/{sanatorium.id}",
        json={"address": "Updated 99"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["address"] == "Updated 99"


async def test_patch_as_other_admin_returns_403(
    client: AsyncClient, db: AsyncSession, admin_headers
) -> None:
    other_admin = await make_user(
        db, email="other-admin@test.com", role=UserRole.ADMIN
    )
    sanatorium = await make_sanatorium(
        db, name="Other", slug="other", admin_user_id=other_admin.id
    )
    resp = await client.patch(
        f"/api/sanatoriums/{sanatorium.id}",
        json={"address": "should not work"},
        headers=admin_headers,
    )
    assert resp.status_code == 403


async def test_patch_as_customer_returns_403(
    client: AsyncClient, db: AsyncSession, customer_headers
) -> None:
    sanatorium = await make_sanatorium(db, slug="s1")
    resp = await client.patch(
        f"/api/sanatoriums/{sanatorium.id}",
        json={"stars": 1},
        headers=customer_headers,
    )
    assert resp.status_code == 403


async def test_patch_merges_partial_translations(
    client: AsyncClient, db: AsyncSession, super_admin_headers
) -> None:
    sanatorium = await make_sanatorium(
        db,
        slug="merge-target",
        description={"uz": "Eski uz", "ru": "Старый ru", "en": "Old en"},
    )
    resp = await client.patch(
        f"/api/sanatoriums/{sanatorium.id}",
        json={"description": {"uz": "Yangi uz"}},
        headers=super_admin_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()["description"]
    assert body["uz"] == "Yangi uz"
    assert body["ru"] == "Старый ru"
    assert body["en"] == "Old en"


async def test_patch_translation_null_clears_single_locale(
    client: AsyncClient, db: AsyncSession, super_admin_headers
) -> None:
    sanatorium = await make_sanatorium(
        db,
        slug="clear-target",
        description={"uz": "X", "ru": "Y", "en": "Z"},
    )
    resp = await client.patch(
        f"/api/sanatoriums/{sanatorium.id}",
        json={"description": {"ru": None}},
        headers=super_admin_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()["description"]
    assert body["uz"] == "X"
    assert body["ru"] is None
    assert body["en"] == "Z"


async def test_patch_not_found_returns_404(
    client: AsyncClient, super_admin_headers
) -> None:
    resp = await client.patch(
        f"/api/sanatoriums/{uuid.uuid4()}",
        json={"stars": 3},
        headers=super_admin_headers,
    )
    assert resp.status_code == 404


# ---------- approve ----------


async def test_approve_as_super_admin(
    client: AsyncClient, db: AsyncSession, super_admin_headers
) -> None:
    sanatorium = await make_sanatorium(
        db, slug="pending-one", status=SanatoriumStatus.PENDING
    )
    resp = await client.post(
        f"/api/sanatoriums/{sanatorium.id}/approve", headers=super_admin_headers
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"


async def test_approve_already_approved_returns_409(
    client: AsyncClient, db: AsyncSession, super_admin_headers
) -> None:
    sanatorium = await make_sanatorium(db, slug="already")
    resp = await client.post(
        f"/api/sanatoriums/{sanatorium.id}/approve", headers=super_admin_headers
    )
    assert resp.status_code == 409


async def test_approve_as_admin_returns_403(
    client: AsyncClient, db: AsyncSession, admin_headers
) -> None:
    sanatorium = await make_sanatorium(
        db, slug="needs-approval", status=SanatoriumStatus.PENDING
    )
    resp = await client.post(
        f"/api/sanatoriums/{sanatorium.id}/approve", headers=admin_headers
    )
    assert resp.status_code == 403


async def test_approve_not_found_returns_404(
    client: AsyncClient, super_admin_headers
) -> None:
    resp = await client.post(
        f"/api/sanatoriums/{uuid.uuid4()}/approve", headers=super_admin_headers
    )
    assert resp.status_code == 404


# ---------- list visibility ----------


async def test_list_public_only_approved(
    client: AsyncClient, db: AsyncSession
) -> None:
    await make_sanatorium(db, slug="ok", status=SanatoriumStatus.APPROVED)
    await make_sanatorium(db, slug="not-ok", status=SanatoriumStatus.PENDING)
    resp = await client.get("/api/sanatoriums")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["slug"] == "ok"


async def test_list_super_admin_sees_all(
    client: AsyncClient, db: AsyncSession, super_admin_headers
) -> None:
    await make_sanatorium(db, slug="a", status=SanatoriumStatus.APPROVED)
    await make_sanatorium(db, slug="b", status=SanatoriumStatus.PENDING)
    await make_sanatorium(db, slug="c", status=SanatoriumStatus.REJECTED)
    resp = await client.get("/api/sanatoriums", headers=super_admin_headers)
    assert resp.json()["total"] == 3


async def test_list_admin_sees_approved_and_own(
    client: AsyncClient, db: AsyncSession, admin_user, admin_headers
) -> None:
    # Admin sees the public catalogue (approved properties of all owners) plus
    # their own draft/pending/rejected listings — they should never be locked
    # out of their own work even before approval.
    await make_sanatorium(db, slug="mine-pending", admin_user_id=admin_user.id,
                         status=SanatoriumStatus.PENDING)
    await make_sanatorium(db, slug="someone-else-approved")
    await make_sanatorium(db, slug="someone-else-pending",
                         status=SanatoriumStatus.PENDING)
    resp = await client.get("/api/sanatoriums", headers=admin_headers)
    slugs = {item["slug"] for item in resp.json()["items"]}
    assert slugs == {"mine-pending", "someone-else-approved"}


# ---------- list filters / search / sort ----------


async def test_list_filter_city(client: AsyncClient, db: AsyncSession) -> None:
    await make_sanatorium(db, slug="tash", city="Toshkent")
    await make_sanatorium(db, slug="sam", city="Samarqand")
    resp = await client.get("/api/sanatoriums?city=Samarqand")
    assert resp.json()["total"] == 1
    assert resp.json()["items"][0]["city"] == "Samarqand"


async def test_list_filter_stars(client: AsyncClient, db: AsyncSession) -> None:
    await make_sanatorium(db, slug="three", stars=3)
    await make_sanatorium(db, slug="five", stars=5)
    resp = await client.get("/api/sanatoriums?stars=5")
    assert resp.json()["total"] == 1


async def test_list_filter_status_super_admin(
    client: AsyncClient, db: AsyncSession, super_admin_headers
) -> None:
    await make_sanatorium(db, slug="ok", status=SanatoriumStatus.APPROVED)
    await make_sanatorium(db, slug="wait", status=SanatoriumStatus.PENDING)
    resp = await client.get(
        "/api/sanatoriums?status=pending", headers=super_admin_headers
    )
    assert resp.json()["total"] == 1
    assert resp.json()["items"][0]["status"] == "pending"


async def test_list_search_name(client: AsyncClient, db: AsyncSession) -> None:
    await make_sanatorium(db, name="Vodiy Shifosi", slug="vodiy")
    await make_sanatorium(db, name="Yangi Hayot", slug="yangi")
    resp = await client.get("/api/sanatoriums?q=vodi")
    assert resp.json()["total"] == 1
    assert resp.json()["items"][0]["name"]["uz"] == "Vodiy Shifosi"


async def test_list_search_escapes_wildcards(
    client: AsyncClient, db: AsyncSession
) -> None:
    await make_sanatorium(db, name="Real Name", slug="real")
    # `%` should be literal, not match-all
    resp = await client.get("/api/sanatoriums?q=%25")
    assert resp.json()["total"] == 0


async def test_list_sort_by_name(client: AsyncClient, db: AsyncSession) -> None:
    await make_sanatorium(db, name="Charlie", slug="c")
    await make_sanatorium(db, name="Alpha", slug="a")
    await make_sanatorium(db, name="Bravo", slug="b")
    resp = await client.get("/api/sanatoriums?sort=name")
    assert [s["name"]["uz"] for s in resp.json()["items"]] == [
        "Alpha", "Bravo", "Charlie"
    ]


async def test_list_sort_by_stars_desc(
    client: AsyncClient, db: AsyncSession
) -> None:
    await make_sanatorium(db, slug="s2", stars=2)
    await make_sanatorium(db, slug="s5", stars=5)
    await make_sanatorium(db, slug="s3", stars=3)
    resp = await client.get("/api/sanatoriums?sort=-stars")
    assert [s["stars"] for s in resp.json()["items"]] == [5, 3, 2]


async def test_list_invalid_sort_returns_422(client: AsyncClient) -> None:
    resp = await client.get("/api/sanatoriums?sort=banana")
    assert resp.status_code == 422


async def test_list_pagination(client: AsyncClient, db: AsyncSession) -> None:
    for i in range(5):
        await make_sanatorium(db, name=f"S {i}", slug=f"s{i}")
    resp = await client.get("/api/sanatoriums?limit=2&offset=0")
    body = resp.json()
    assert body["total"] == 5
    assert len(body["items"]) == 2


# ---------- detail visibility ----------


async def test_get_public_approved(client: AsyncClient, db: AsyncSession) -> None:
    sanatorium = await make_sanatorium(db, slug="open")
    resp = await client.get(f"/api/sanatoriums/{sanatorium.id}")
    assert resp.status_code == 200
    assert resp.json()["slug"] == "open"


async def test_get_public_pending_returns_404(
    client: AsyncClient, db: AsyncSession
) -> None:
    sanatorium = await make_sanatorium(
        db, slug="hidden", status=SanatoriumStatus.PENDING
    )
    resp = await client.get(f"/api/sanatoriums/{sanatorium.id}")
    assert resp.status_code == 404


async def test_get_super_admin_pending(
    client: AsyncClient, db: AsyncSession, super_admin_headers
) -> None:
    sanatorium = await make_sanatorium(
        db, slug="pending2", status=SanatoriumStatus.PENDING
    )
    resp = await client.get(
        f"/api/sanatoriums/{sanatorium.id}", headers=super_admin_headers
    )
    assert resp.status_code == 200


async def test_get_admin_other_pending_returns_404(
    client: AsyncClient, db: AsyncSession, admin_headers
) -> None:
    other_admin = await make_user(
        db, email="o-admin@test.com", role=UserRole.ADMIN
    )
    sanatorium = await make_sanatorium(
        db,
        slug="other-pending",
        status=SanatoriumStatus.PENDING,
        admin_user_id=other_admin.id,
    )
    resp = await client.get(
        f"/api/sanatoriums/{sanatorium.id}", headers=admin_headers
    )
    assert resp.status_code == 404
