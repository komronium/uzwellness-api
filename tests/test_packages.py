import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.user import User, UserRole
from tests.factories import make_png, make_room, make_sanatorium

PNG = make_png()


@pytest.fixture
async def package_sanatorium(db: AsyncSession, admin_user):
    return await make_sanatorium(
        db, slug="pkg-host", name="Pkg Host", admin_user_id=admin_user.id
    )


@pytest.fixture
async def usd_room(db: AsyncSession, package_sanatorium):
    return await make_room(db, sanatorium=package_sanatorium, base_currency="USD")


def _payload(sanatorium_id: uuid.UUID, room_id: uuid.UUID, **overrides) -> dict:
    base = {
        "title": {
            "uz": "Toshkent Wellness Sayohati",
            "ru": "Велнес-путешествие в Ташкент",
            "en": "Tashkent Wellness Journey",
        },
        "description": {
            "uz": "5 kunlik dam olish dasturi.",
            "ru": "5-дневная оздоровительная программа.",
            "en": "5-day wellness retreat.",
        },
        "duration_nights": 5,
        "base_price": "1290.00",
        "currency": "USD",
        "sanatorium_id": str(sanatorium_id),
        "room_id": str(room_id),
        "items": [
            {
                "item_type": "flight",
                "title": {"uz": "Parvoz", "ru": "Перелёт", "en": "Round-trip flight"},
                "is_included": True,
            },
            {
                "item_type": "treatment",
                "title": {"uz": "Massaj", "ru": "Массаж", "en": "Massage"},
                "is_included": True,
            },
            {
                "item_type": "excursion",
                "title": {"uz": "Chimg'on", "ru": "Экскурсия", "en": "Chimgan tour"},
                "is_included": False,
                "extra_price": "120.00",
            },
        ],
    }
    base.update(overrides)
    return base


# ── create ───────────────────────────────────────────────────────────────────


async def test_sanatorium_admin_creates_package(
    client: AsyncClient, package_sanatorium, usd_room, admin_headers
) -> None:
    resp = await client.post(
        "/api/packages",
        json=_payload(package_sanatorium.id, usd_room.id),
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["title"]["uz"] == "Toshkent Wellness Sayohati"
    assert body["slug"] == "toshkent-wellness-sayohati"
    assert body["duration_nights"] == 5
    assert body["base_price"] == "1290.00"
    assert body["sanatorium_id"] == str(package_sanatorium.id)
    assert body["room_id"] == str(usd_room.id)
    assert body["is_featured"] is False
    assert body["display_order"] == 0
    assert len(body["items"]) == 3


async def test_super_admin_cannot_create_package(
    client: AsyncClient, package_sanatorium, usd_room, super_admin_headers
) -> None:
    resp = await client.post(
        "/api/packages",
        json=_payload(package_sanatorium.id, usd_room.id),
        headers=super_admin_headers,
    )
    assert resp.status_code == 403


async def test_customer_cannot_create_package(
    client: AsyncClient, package_sanatorium, usd_room, customer_headers
) -> None:
    resp = await client.post(
        "/api/packages",
        json=_payload(package_sanatorium.id, usd_room.id),
        headers=customer_headers,
    )
    assert resp.status_code == 403


async def test_room_id_is_required(
    client: AsyncClient, package_sanatorium, admin_headers, super_admin_headers
) -> None:
    payload = _payload(package_sanatorium.id, uuid.uuid4())
    payload.pop("room_id")
    resp = await client.post("/api/packages", json=payload, headers=admin_headers)
    assert resp.status_code == 422


async def test_sanatorium_id_is_required(
    client: AsyncClient, admin_headers, super_admin_headers
) -> None:
    payload = _payload(uuid.uuid4(), uuid.uuid4())
    payload.pop("sanatorium_id")
    resp = await client.post("/api/packages", json=payload, headers=admin_headers)
    assert resp.status_code == 422


async def test_unknown_sanatorium_returns_400(
    client: AsyncClient, admin_headers, super_admin_headers
) -> None:
    resp = await client.post(
        "/api/packages",
        json=_payload(uuid.uuid4(), uuid.uuid4()),
        headers=admin_headers,
    )
    assert resp.status_code == 400


async def test_unknown_room_returns_400(
    client: AsyncClient, package_sanatorium, admin_headers, super_admin_headers
) -> None:
    resp = await client.post(
        "/api/packages",
        json=_payload(package_sanatorium.id, uuid.uuid4()),
        headers=admin_headers,
    )
    assert resp.status_code == 400


async def test_room_from_different_sanatorium_rejected(
    client: AsyncClient,
    db: AsyncSession,
    package_sanatorium,
    admin_headers,
    super_admin_headers,
) -> None:
    other = await make_sanatorium(db, slug="pkg-other")
    foreign_room = await make_room(db, sanatorium=other, base_currency="USD")
    resp = await client.post(
        "/api/packages",
        json=_payload(package_sanatorium.id, foreign_room.id),
        headers=admin_headers,
    )
    assert resp.status_code == 400


async def test_room_currency_mismatch_rejected(
    client: AsyncClient,
    db: AsyncSession,
    package_sanatorium,
    admin_headers,
    super_admin_headers,
) -> None:
    uzs_room = await make_room(
        db,
        sanatorium=package_sanatorium,
        base_currency="UZS",
        base_price="1000000",
    )
    resp = await client.post(
        "/api/packages",
        json=_payload(package_sanatorium.id, uzs_room.id, currency="USD"),
        headers=admin_headers,
    )
    assert resp.status_code == 400


async def test_inactive_room_rejected_on_create(
    client: AsyncClient,
    db: AsyncSession,
    package_sanatorium,
    admin_headers,
    super_admin_headers,
) -> None:
    inactive_room = await make_room(
        db,
        sanatorium=package_sanatorium,
        base_currency="USD",
        is_active=False,
    )
    resp = await client.post(
        "/api/packages",
        json=_payload(package_sanatorium.id, inactive_room.id),
        headers=admin_headers,
    )
    assert resp.status_code == 400
    assert "inactive" in resp.json()["detail"].lower()


async def test_create_requires_all_three_locales(
    client: AsyncClient,
    package_sanatorium,
    usd_room,
    admin_headers,
    super_admin_headers,
) -> None:
    payload = _payload(package_sanatorium.id, usd_room.id, title={"uz": "Faqat uz"})
    resp = await client.post("/api/packages", json=payload, headers=admin_headers)
    assert resp.status_code == 422


async def test_hotel_item_type_rejected(
    client: AsyncClient,
    package_sanatorium,
    usd_room,
    admin_headers,
    super_admin_headers,
) -> None:
    payload = _payload(package_sanatorium.id, usd_room.id)
    payload["items"].append(
        {
            "item_type": "hotel",
            "title": {"uz": "X", "ru": "X", "en": "X"},
            "is_included": True,
        }
    )
    resp = await client.post("/api/packages", json=payload, headers=admin_headers)
    assert resp.status_code == 422


# ── list / get ────────────────────────────────────────────────────────────────


async def test_public_list_returns_resolved_strings(
    client: AsyncClient,
    package_sanatorium,
    usd_room,
    admin_headers,
    super_admin_headers,
) -> None:
    await client.post(
        "/api/packages",
        json=_payload(package_sanatorium.id, usd_room.id),
        headers=admin_headers,
    )
    resp = await client.get("/api/packages?lang=ru")
    assert resp.status_code == 200
    item = resp.json()["items"][0]
    assert item["title"] == "Велнес-путешествие в Ташкент"
    assert isinstance(item["title"], str)


async def test_include_translations_returns_dict(
    client: AsyncClient,
    package_sanatorium,
    usd_room,
    admin_headers,
    super_admin_headers,
) -> None:
    payload = _payload(package_sanatorium.id, usd_room.id)
    await client.post("/api/packages", json=payload, headers=admin_headers)
    resp = await client.get(
        "/api/packages?include_translations=true", headers=super_admin_headers
    )
    item = resp.json()["items"][0]
    assert item["title"] == payload["title"]


async def test_public_list_hides_inactive_even_if_requested(
    client: AsyncClient,
    package_sanatorium,
    usd_room,
    admin_headers,
    super_admin_headers,
) -> None:
    created = await client.post(
        "/api/packages",
        json=_payload(package_sanatorium.id, usd_room.id),
        headers=admin_headers,
    )
    pid = created.json()["id"]
    await client.patch(
        f"/api/packages/{pid}",
        json={"is_active": False},
        headers=super_admin_headers,
    )

    resp = await client.get("/api/packages?active_only=false")

    assert resp.status_code == 200
    assert resp.json()["total"] == 0


async def test_super_admin_can_list_inactive_packages(
    client: AsyncClient,
    package_sanatorium,
    usd_room,
    admin_headers,
    super_admin_headers,
) -> None:
    created = await client.post(
        "/api/packages",
        json=_payload(package_sanatorium.id, usd_room.id),
        headers=admin_headers,
    )
    pid = created.json()["id"]
    await client.patch(
        f"/api/packages/{pid}",
        json={"is_active": False},
        headers=super_admin_headers,
    )

    resp = await client.get(
        "/api/packages?active_only=false", headers=super_admin_headers
    )

    assert resp.status_code == 200
    assert resp.json()["total"] == 1


async def test_public_detail_hides_inactive_package(
    client: AsyncClient,
    package_sanatorium,
    usd_room,
    admin_headers,
    super_admin_headers,
) -> None:
    created = await client.post(
        "/api/packages",
        json=_payload(package_sanatorium.id, usd_room.id),
        headers=admin_headers,
    )
    pid = created.json()["id"]
    await client.patch(
        f"/api/packages/{pid}",
        json={"is_active": False},
        headers=super_admin_headers,
    )

    resp = await client.get("/api/packages/toshkent-wellness-sayohati")

    assert resp.status_code == 404


async def test_featured_packages_endpoint_orders_by_display_order(
    client: AsyncClient,
    package_sanatorium,
    usd_room,
    admin_headers,
    super_admin_headers,
) -> None:
    second = _payload(
        package_sanatorium.id,
        usd_room.id,
        title={"uz": "Ikkinchi", "ru": "Второй", "en": "Second"},
        is_featured=True,
        display_order=2,
    )
    first = _payload(
        package_sanatorium.id,
        usd_room.id,
        title={"uz": "Birinchi", "ru": "Первый", "en": "First"},
        is_featured=True,
        display_order=1,
    )
    hidden = _payload(
        package_sanatorium.id,
        usd_room.id,
        title={"uz": "Oddiy", "ru": "Обычный", "en": "Regular"},
        is_featured=False,
        display_order=0,
    )
    second_created = await client.post(
        "/api/packages", json=second, headers=admin_headers
    )
    first_created = await client.post(
        "/api/packages", json=first, headers=admin_headers
    )
    await client.post("/api/packages", json=hidden, headers=admin_headers)
    await client.patch(
        f"/api/packages/{second_created.json()['id']}",
        json={"is_featured": True, "display_order": 2},
        headers=super_admin_headers,
    )
    await client.patch(
        f"/api/packages/{first_created.json()['id']}",
        json={"is_featured": True, "display_order": 1},
        headers=super_admin_headers,
    )

    resp = await client.get("/api/packages/featured?lang=en")

    assert resp.status_code == 200
    assert [item["title"] for item in resp.json()["items"]] == ["First", "Second"]


async def test_list_filters_by_duration(
    client: AsyncClient,
    package_sanatorium,
    usd_room,
    admin_headers,
    super_admin_headers,
) -> None:
    short = _payload(
        package_sanatorium.id,
        usd_room.id,
        duration_nights=3,
        title={"uz": "Qisqa", "ru": "Короткий", "en": "Short"},
    )
    long_ = _payload(
        package_sanatorium.id,
        usd_room.id,
        duration_nights=10,
        title={"uz": "Uzun", "ru": "Длинный", "en": "Long"},
    )
    await client.post("/api/packages", json=short, headers=admin_headers)
    await client.post("/api/packages", json=long_, headers=admin_headers)
    resp = await client.get("/api/packages?duration_max=5&lang=uz")
    titles = [p["title"] for p in resp.json()["items"]]
    assert "Qisqa" in titles and "Uzun" not in titles


async def test_list_filters_by_price(
    client: AsyncClient,
    package_sanatorium,
    usd_room,
    admin_headers,
    super_admin_headers,
) -> None:
    cheap = _payload(
        package_sanatorium.id,
        usd_room.id,
        base_price="500.00",
        title={"uz": "Arzon", "ru": "Дёшево", "en": "Cheap"},
    )
    pricey = _payload(
        package_sanatorium.id,
        usd_room.id,
        base_price="5000.00",
        title={"uz": "Qimmat", "ru": "Дорого", "en": "Pricey"},
    )
    await client.post("/api/packages", json=cheap, headers=admin_headers)
    await client.post("/api/packages", json=pricey, headers=admin_headers)
    resp = await client.get("/api/packages?price_max=1000&lang=uz")
    titles = [p["title"] for p in resp.json()["items"]]
    assert "Arzon" in titles and "Qimmat" not in titles


async def test_get_by_slug_works(
    client: AsyncClient,
    package_sanatorium,
    usd_room,
    admin_headers,
    super_admin_headers,
) -> None:
    await client.post(
        "/api/packages",
        json=_payload(package_sanatorium.id, usd_room.id),
        headers=admin_headers,
    )
    resp = await client.get("/api/packages/toshkent-wellness-sayohati")
    assert resp.status_code == 200
    assert resp.json()["slug"] == "toshkent-wellness-sayohati"


async def test_upload_package_hero_image_as_super_admin(
    client: AsyncClient,
    package_sanatorium,
    usd_room,
    admin_headers,
    super_admin_headers,
    storage,
) -> None:
    created = await client.post(
        "/api/packages",
        json=_payload(package_sanatorium.id, usd_room.id),
        headers=admin_headers,
    )
    pid = created.json()["id"]

    resp = await client.post(
        f"/api/packages/{pid}/hero-image",
        headers=super_admin_headers,
        files={"file": ("hero.png", PNG, "image/png")},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["hero_image_url"].endswith(".webp")
    key = body["hero_image_url"].removeprefix(storage.url_prefix + "/")
    assert key in storage.objects
    assert storage.objects[key].startswith(b"RIFF")
    assert storage.objects[key][8:12] == b"WEBP"


async def test_delete_package_hero_image(
    client: AsyncClient,
    package_sanatorium,
    usd_room,
    admin_headers,
    super_admin_headers,
    storage,
) -> None:
    created = await client.post(
        "/api/packages",
        json=_payload(package_sanatorium.id, usd_room.id),
        headers=admin_headers,
    )
    pid = created.json()["id"]
    uploaded = await client.post(
        f"/api/packages/{pid}/hero-image",
        headers=super_admin_headers,
        files={"file": ("hero.png", PNG, "image/png")},
    )
    key = uploaded.json()["hero_image_url"].removeprefix(storage.url_prefix + "/")

    resp = await client.delete(
        f"/api/packages/{pid}/hero-image", headers=super_admin_headers
    )

    assert resp.status_code == 200
    assert resp.json()["hero_image_url"] is None
    assert key not in storage.objects


async def test_get_not_found_returns_404(client: AsyncClient) -> None:
    resp = await client.get(f"/api/packages/{uuid.uuid4()}")
    assert resp.status_code == 404


# ── patch ────────────────────────────────────────────────────────────────────


async def test_patch_merges_translations(
    client: AsyncClient,
    package_sanatorium,
    usd_room,
    admin_headers,
    super_admin_headers,
) -> None:
    created = await client.post(
        "/api/packages",
        json=_payload(package_sanatorium.id, usd_room.id),
        headers=admin_headers,
    )
    pid = created.json()["id"]
    resp = await client.patch(
        f"/api/packages/{pid}",
        json={"title": {"uz": "Yangi nom"}},
        headers=super_admin_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["title"]["uz"] == "Yangi nom"
    assert body["title"]["en"] == "Tashkent Wellness Journey"


async def test_patch_room_swap_validates(
    client: AsyncClient,
    db: AsyncSession,
    package_sanatorium,
    usd_room,
    admin_headers,
    super_admin_headers,
) -> None:
    created = await client.post(
        "/api/packages",
        json=_payload(package_sanatorium.id, usd_room.id),
        headers=admin_headers,
    )
    pid = created.json()["id"]
    other = await make_sanatorium(db, slug="pkg-other-2")
    foreign = await make_room(db, sanatorium=other, base_currency="USD")
    resp = await client.patch(
        f"/api/packages/{pid}",
        json={"room_id": str(foreign.id)},
        headers=super_admin_headers,
    )
    assert resp.status_code == 400


async def test_patch_currency_alone_must_match_room(
    client: AsyncClient,
    db: AsyncSession,
    package_sanatorium,
    usd_room,
    admin_headers,
    super_admin_headers,
) -> None:
    # Package was created USD/USD-room. Switching currency to UZS without
    # also swapping to a UZS room must be rejected — otherwise the booking
    # records the wrong currency snapshot.
    created = await client.post(
        "/api/packages",
        json=_payload(package_sanatorium.id, usd_room.id),
        headers=admin_headers,
    )
    pid = created.json()["id"]
    resp = await client.patch(
        f"/api/packages/{pid}",
        json={"currency": "UZS", "base_price": "1000000.00"},
        headers=super_admin_headers,
    )
    assert resp.status_code == 400


# ── items CRUD ───────────────────────────────────────────────────────────────


async def test_add_and_delete_item(
    client: AsyncClient,
    package_sanatorium,
    usd_room,
    admin_headers,
    super_admin_headers,
) -> None:
    created = await client.post(
        "/api/packages",
        json=_payload(package_sanatorium.id, usd_room.id),
        headers=admin_headers,
    )
    pid = created.json()["id"]
    add = await client.post(
        f"/api/packages/{pid}/items",
        json={
            "item_type": "meal",
            "title": {"uz": "Nonushta", "ru": "Завтрак", "en": "Breakfast"},
            "is_included": True,
        },
        headers=super_admin_headers,
    )
    assert add.status_code == 201, add.text
    item_id = add.json()["id"]

    detail = await client.get(f"/api/packages/{pid}?include_translations=true")
    types = [i["item_type"] for i in detail.json()["items"]]
    assert "meal" in types

    delete = await client.delete(
        f"/api/packages/{pid}/items/{item_id}", headers=super_admin_headers
    )
    assert delete.status_code == 204


# ── delete ───────────────────────────────────────────────────────────────────


async def test_delete_package(
    client: AsyncClient,
    package_sanatorium,
    usd_room,
    admin_headers,
    super_admin_headers,
) -> None:
    created = await client.post(
        "/api/packages",
        json=_payload(package_sanatorium.id, usd_room.id),
        headers=admin_headers,
    )
    pid = created.json()["id"]
    resp = await client.delete(f"/api/packages/{pid}", headers=super_admin_headers)
    assert resp.status_code == 204
    get_resp = await client.get(f"/api/packages/{pid}")
    assert get_resp.status_code == 404


# ── edit permissions (tasks 5 & 6) ───────────────────────────────────────────


async def _make_package(client, sanatorium_id, room_id, headers) -> str:
    created = await client.post(
        "/api/packages",
        json=_payload(sanatorium_id, room_id),
        headers=headers,
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


async def test_owner_admin_can_edit_own_package(
    client: AsyncClient, package_sanatorium, usd_room, admin_headers
) -> None:
    pid = await _make_package(client, package_sanatorium.id, usd_room.id, admin_headers)
    resp = await client.patch(
        f"/api/packages/{pid}",
        json={"base_price": "999.00", "title": {"uz": "Yangilangan"}},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["base_price"] == "999.00"
    assert resp.json()["title"]["uz"] == "Yangilangan"


async def test_admin_cannot_feature_own_package(
    client: AsyncClient, package_sanatorium, usd_room, admin_headers
) -> None:
    pid = await _make_package(client, package_sanatorium.id, usd_room.id, admin_headers)
    resp = await client.patch(
        f"/api/packages/{pid}",
        json={"is_featured": True},
        headers=admin_headers,
    )
    assert resp.status_code == 403
    assert "super_admin" in resp.json()["detail"]
    assert "is_featured" in resp.json()["detail"]


async def test_admin_cannot_set_display_order(
    client: AsyncClient, package_sanatorium, usd_room, admin_headers
) -> None:
    pid = await _make_package(client, package_sanatorium.id, usd_room.id, admin_headers)
    resp = await client.patch(
        f"/api/packages/{pid}",
        json={"display_order": 3},
        headers=admin_headers,
    )
    assert resp.status_code == 403


async def test_super_admin_can_feature_package(
    client: AsyncClient, package_sanatorium, usd_room, admin_headers, super_admin_headers
) -> None:
    pid = await _make_package(client, package_sanatorium.id, usd_room.id, admin_headers)
    resp = await client.patch(
        f"/api/packages/{pid}",
        json={"is_featured": True, "display_order": 1},
        headers=super_admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_featured"] is True
    assert resp.json()["display_order"] == 1


async def test_admin_cannot_edit_other_sanatoriums_package(
    client: AsyncClient,
    db: AsyncSession,
    package_sanatorium,
    usd_room,
    admin_headers,
) -> None:
    pid = await _make_package(client, package_sanatorium.id, usd_room.id, admin_headers)
    other_admin = User(
        email="other-admin@test.com",
        password_hash=hash_password("otherpass123"),
        role=UserRole.ADMIN,
        full_name="Other Admin",
        is_active=True,
    )
    db.add(other_admin)
    await db.commit()
    login = await client.post(
        "/api/auth/login",
        json={"email": "other-admin@test.com", "password": "otherpass123"},
    )
    other_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = await client.patch(
        f"/api/packages/{pid}",
        json={"base_price": "1.00"},
        headers=other_headers,
    )
    assert resp.status_code == 403


async def test_owner_admin_can_manage_items(
    client: AsyncClient, package_sanatorium, usd_room, admin_headers
) -> None:
    pid = await _make_package(client, package_sanatorium.id, usd_room.id, admin_headers)
    add = await client.post(
        f"/api/packages/{pid}/items",
        json={
            "item_type": "meal",
            "title": {"uz": "Nonushta", "ru": "Завтрак", "en": "Breakfast"},
            "is_included": True,
        },
        headers=admin_headers,
    )
    assert add.status_code == 201, add.text
    item_id = add.json()["id"]
    delete = await client.delete(
        f"/api/packages/{pid}/items/{item_id}", headers=admin_headers
    )
    assert delete.status_code == 204
