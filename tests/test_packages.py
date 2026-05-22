import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import make_sanatorium
from tests.test_availability import make_room


@pytest.fixture
async def package_sanatorium(db: AsyncSession):
    return await make_sanatorium(db, slug="pkg-host", name="Pkg Host")


@pytest.fixture
async def usd_room(db: AsyncSession, package_sanatorium):
    return await make_room(
        db, sanatorium=package_sanatorium, base_currency="USD"
    )


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


async def test_super_admin_creates_package(
    client: AsyncClient, package_sanatorium, usd_room, super_admin_headers
) -> None:
    resp = await client.post(
        "/api/packages",
        json=_payload(package_sanatorium.id, usd_room.id),
        headers=super_admin_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["title"]["uz"] == "Toshkent Wellness Sayohati"
    assert body["slug"] == "toshkent-wellness-sayohati"
    assert body["duration_nights"] == 5
    assert body["base_price"] == "1290.00"
    assert body["sanatorium_id"] == str(package_sanatorium.id)
    assert body["room_id"] == str(usd_room.id)
    assert len(body["items"]) == 3


async def test_admin_cannot_create_package(
    client: AsyncClient, package_sanatorium, usd_room, admin_headers
) -> None:
    resp = await client.post(
        "/api/packages",
        json=_payload(package_sanatorium.id, usd_room.id),
        headers=admin_headers,
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
    client: AsyncClient, package_sanatorium, super_admin_headers
) -> None:
    payload = _payload(package_sanatorium.id, uuid.uuid4())
    payload.pop("room_id")
    resp = await client.post(
        "/api/packages", json=payload, headers=super_admin_headers
    )
    assert resp.status_code == 422


async def test_sanatorium_id_is_required(
    client: AsyncClient, super_admin_headers
) -> None:
    payload = _payload(uuid.uuid4(), uuid.uuid4())
    payload.pop("sanatorium_id")
    resp = await client.post(
        "/api/packages", json=payload, headers=super_admin_headers
    )
    assert resp.status_code == 422


async def test_unknown_sanatorium_returns_400(
    client: AsyncClient, super_admin_headers
) -> None:
    resp = await client.post(
        "/api/packages",
        json=_payload(uuid.uuid4(), uuid.uuid4()),
        headers=super_admin_headers,
    )
    assert resp.status_code == 400


async def test_unknown_room_returns_400(
    client: AsyncClient, package_sanatorium, super_admin_headers
) -> None:
    resp = await client.post(
        "/api/packages",
        json=_payload(package_sanatorium.id, uuid.uuid4()),
        headers=super_admin_headers,
    )
    assert resp.status_code == 400


async def test_room_from_different_sanatorium_rejected(
    client: AsyncClient,
    db: AsyncSession,
    package_sanatorium,
    super_admin_headers,
) -> None:
    other = await make_sanatorium(db, slug="pkg-other")
    foreign_room = await make_room(db, sanatorium=other, base_currency="USD")
    resp = await client.post(
        "/api/packages",
        json=_payload(package_sanatorium.id, foreign_room.id),
        headers=super_admin_headers,
    )
    assert resp.status_code == 400


async def test_room_currency_mismatch_rejected(
    client: AsyncClient,
    db: AsyncSession,
    package_sanatorium,
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
        headers=super_admin_headers,
    )
    assert resp.status_code == 400


async def test_inactive_room_rejected_on_create(
    client: AsyncClient,
    db: AsyncSession,
    package_sanatorium,
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
        headers=super_admin_headers,
    )
    assert resp.status_code == 400
    assert "inactive" in resp.json()["detail"].lower()


async def test_create_requires_all_three_locales(
    client: AsyncClient, package_sanatorium, usd_room, super_admin_headers
) -> None:
    payload = _payload(package_sanatorium.id, usd_room.id, title={"uz": "Faqat uz"})
    resp = await client.post(
        "/api/packages", json=payload, headers=super_admin_headers
    )
    assert resp.status_code == 422


async def test_hotel_item_type_rejected(
    client: AsyncClient, package_sanatorium, usd_room, super_admin_headers
) -> None:
    payload = _payload(package_sanatorium.id, usd_room.id)
    payload["items"].append(
        {
            "item_type": "hotel",
            "title": {"uz": "X", "ru": "X", "en": "X"},
            "is_included": True,
        }
    )
    resp = await client.post(
        "/api/packages", json=payload, headers=super_admin_headers
    )
    assert resp.status_code == 422


# ── list / get ────────────────────────────────────────────────────────────────


async def test_public_list_returns_resolved_strings(
    client: AsyncClient, package_sanatorium, usd_room, super_admin_headers
) -> None:
    await client.post(
        "/api/packages",
        json=_payload(package_sanatorium.id, usd_room.id),
        headers=super_admin_headers,
    )
    resp = await client.get("/api/packages?lang=ru")
    assert resp.status_code == 200
    item = resp.json()["items"][0]
    assert item["title"] == "Велнес-путешествие в Ташкент"
    assert isinstance(item["title"], str)


async def test_include_translations_returns_dict(
    client: AsyncClient, package_sanatorium, usd_room, super_admin_headers
) -> None:
    payload = _payload(package_sanatorium.id, usd_room.id)
    await client.post("/api/packages", json=payload, headers=super_admin_headers)
    resp = await client.get("/api/packages?include_translations=true")
    item = resp.json()["items"][0]
    assert item["title"] == payload["title"]


async def test_list_filters_by_duration(
    client: AsyncClient, package_sanatorium, usd_room, super_admin_headers
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
    await client.post("/api/packages", json=short, headers=super_admin_headers)
    await client.post("/api/packages", json=long_, headers=super_admin_headers)
    resp = await client.get("/api/packages?duration_max=5&lang=uz")
    titles = [p["title"] for p in resp.json()["items"]]
    assert "Qisqa" in titles and "Uzun" not in titles


async def test_list_filters_by_price(
    client: AsyncClient, package_sanatorium, usd_room, super_admin_headers
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
    await client.post("/api/packages", json=cheap, headers=super_admin_headers)
    await client.post("/api/packages", json=pricey, headers=super_admin_headers)
    resp = await client.get("/api/packages?price_max=1000&lang=uz")
    titles = [p["title"] for p in resp.json()["items"]]
    assert "Arzon" in titles and "Qimmat" not in titles


async def test_get_by_slug_works(
    client: AsyncClient, package_sanatorium, usd_room, super_admin_headers
) -> None:
    await client.post(
        "/api/packages",
        json=_payload(package_sanatorium.id, usd_room.id),
        headers=super_admin_headers,
    )
    resp = await client.get("/api/packages/toshkent-wellness-sayohati")
    assert resp.status_code == 200
    assert resp.json()["slug"] == "toshkent-wellness-sayohati"


async def test_get_not_found_returns_404(client: AsyncClient) -> None:
    resp = await client.get(f"/api/packages/{uuid.uuid4()}")
    assert resp.status_code == 404


# ── patch ────────────────────────────────────────────────────────────────────


async def test_patch_merges_translations(
    client: AsyncClient, package_sanatorium, usd_room, super_admin_headers
) -> None:
    created = await client.post(
        "/api/packages",
        json=_payload(package_sanatorium.id, usd_room.id),
        headers=super_admin_headers,
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
    super_admin_headers,
) -> None:
    created = await client.post(
        "/api/packages",
        json=_payload(package_sanatorium.id, usd_room.id),
        headers=super_admin_headers,
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
    super_admin_headers,
) -> None:
    # Package was created USD/USD-room. Switching currency to UZS without
    # also swapping to a UZS room must be rejected — otherwise the booking
    # records the wrong currency snapshot.
    created = await client.post(
        "/api/packages",
        json=_payload(package_sanatorium.id, usd_room.id),
        headers=super_admin_headers,
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
    client: AsyncClient, package_sanatorium, usd_room, super_admin_headers
) -> None:
    created = await client.post(
        "/api/packages",
        json=_payload(package_sanatorium.id, usd_room.id),
        headers=super_admin_headers,
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
    client: AsyncClient, package_sanatorium, usd_room, super_admin_headers
) -> None:
    created = await client.post(
        "/api/packages",
        json=_payload(package_sanatorium.id, usd_room.id),
        headers=super_admin_headers,
    )
    pid = created.json()["id"]
    resp = await client.delete(f"/api/packages/{pid}", headers=super_admin_headers)
    assert resp.status_code == 204
    get_resp = await client.get(f"/api/packages/{pid}")
    assert get_resp.status_code == 404
