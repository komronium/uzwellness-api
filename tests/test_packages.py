import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import make_sanatorium


CREATE_PAYLOAD = {
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
    "items": [
        {
            "item_type": "flight",
            "title": {"uz": "Parvoz", "ru": "Перелёт", "en": "Round-trip flight"},
            "is_included": True,
        },
        {
            "item_type": "hotel",
            "title": {"uz": "4 yulduzli mehmonxona", "ru": "Отель 4*", "en": "4-star hotel"},
            "is_included": True,
        },
        {
            "item_type": "excursion",
            "title": {"uz": "Chimg'on ekskursiyasi", "ru": "Экскурсия", "en": "Chimgan tour"},
            "is_included": False,
            "extra_price": "120.00",
        },
    ],
}


# ── create ───────────────────────────────────────────────────────────────────


async def test_super_admin_creates_package(
    client: AsyncClient, super_admin_headers
) -> None:
    resp = await client.post(
        "/api/packages", json=CREATE_PAYLOAD, headers=super_admin_headers
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["title"]["uz"] == "Toshkent Wellness Sayohati"
    assert body["slug"] == "toshkent-wellness-sayohati"
    assert body["duration_nights"] == 5
    assert body["base_price"] == "1290.00"
    assert len(body["items"]) == 3
    types = [i["item_type"] for i in body["items"]]
    assert "flight" in types and "excursion" in types
    excursion = next(i for i in body["items"] if i["item_type"] == "excursion")
    assert excursion["is_included"] is False
    assert excursion["extra_price"] == "120.00"


async def test_admin_cannot_create_package(
    client: AsyncClient, admin_headers
) -> None:
    resp = await client.post(
        "/api/packages", json=CREATE_PAYLOAD, headers=admin_headers
    )
    assert resp.status_code == 403


async def test_customer_cannot_create_package(
    client: AsyncClient, customer_headers
) -> None:
    resp = await client.post(
        "/api/packages", json=CREATE_PAYLOAD, headers=customer_headers
    )
    assert resp.status_code == 403


async def test_create_requires_all_three_locales(
    client: AsyncClient, super_admin_headers
) -> None:
    payload = {**CREATE_PAYLOAD, "title": {"uz": "Faqat uz"}}
    resp = await client.post(
        "/api/packages", json=payload, headers=super_admin_headers
    )
    assert resp.status_code == 422


async def test_create_with_sanatorium_link(
    client: AsyncClient, db: AsyncSession, super_admin_headers
) -> None:
    san = await make_sanatorium(db, slug="linked-san")
    payload = {**CREATE_PAYLOAD, "sanatorium_id": str(san.id)}
    resp = await client.post(
        "/api/packages", json=payload, headers=super_admin_headers
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["sanatorium_id"] == str(san.id)


async def test_create_with_unknown_sanatorium_returns_400(
    client: AsyncClient, super_admin_headers
) -> None:
    payload = {**CREATE_PAYLOAD, "sanatorium_id": str(uuid.uuid4())}
    resp = await client.post(
        "/api/packages", json=payload, headers=super_admin_headers
    )
    assert resp.status_code == 400


# ── list / get ────────────────────────────────────────────────────────────────


async def test_public_list_returns_resolved_strings(
    client: AsyncClient, super_admin_headers
) -> None:
    await client.post(
        "/api/packages", json=CREATE_PAYLOAD, headers=super_admin_headers
    )
    resp = await client.get("/api/packages?lang=ru")
    assert resp.status_code == 200
    item = resp.json()["items"][0]
    assert item["title"] == "Велнес-путешествие в Ташкент"
    assert isinstance(item["title"], str)


async def test_include_translations_returns_dict(
    client: AsyncClient, super_admin_headers
) -> None:
    await client.post(
        "/api/packages", json=CREATE_PAYLOAD, headers=super_admin_headers
    )
    resp = await client.get("/api/packages?include_translations=true")
    item = resp.json()["items"][0]
    assert item["title"] == CREATE_PAYLOAD["title"]


async def test_list_filters_by_duration(
    client: AsyncClient, super_admin_headers
) -> None:
    short = {**CREATE_PAYLOAD, "duration_nights": 3,
             "title": {**CREATE_PAYLOAD["title"], "uz": "Qisqa"}}
    long_ = {**CREATE_PAYLOAD, "duration_nights": 10,
             "title": {**CREATE_PAYLOAD["title"], "uz": "Uzun"}}
    await client.post("/api/packages", json=short, headers=super_admin_headers)
    await client.post("/api/packages", json=long_, headers=super_admin_headers)
    resp = await client.get("/api/packages?duration_max=5&lang=uz")
    titles = [p["title"] for p in resp.json()["items"]]
    assert "Qisqa" in titles and "Uzun" not in titles


async def test_list_filters_by_price(
    client: AsyncClient, super_admin_headers
) -> None:
    cheap = {
        **CREATE_PAYLOAD,
        "base_price": "500.00",
        "title": {**CREATE_PAYLOAD["title"], "uz": "Arzon"},
    }
    pricey = {
        **CREATE_PAYLOAD,
        "base_price": "5000.00",
        "title": {**CREATE_PAYLOAD["title"], "uz": "Qimmat"},
    }
    await client.post("/api/packages", json=cheap, headers=super_admin_headers)
    await client.post("/api/packages", json=pricey, headers=super_admin_headers)
    resp = await client.get("/api/packages?price_max=1000&lang=uz")
    titles = [p["title"] for p in resp.json()["items"]]
    assert "Arzon" in titles and "Qimmat" not in titles


async def test_get_by_slug_works(
    client: AsyncClient, super_admin_headers
) -> None:
    await client.post(
        "/api/packages", json=CREATE_PAYLOAD, headers=super_admin_headers
    )
    resp = await client.get("/api/packages/toshkent-wellness-sayohati")
    assert resp.status_code == 200
    assert resp.json()["slug"] == "toshkent-wellness-sayohati"


async def test_get_not_found_returns_404(client: AsyncClient) -> None:
    resp = await client.get(f"/api/packages/{uuid.uuid4()}")
    assert resp.status_code == 404


# ── patch ────────────────────────────────────────────────────────────────────


async def test_patch_merges_translations(
    client: AsyncClient, super_admin_headers
) -> None:
    created = await client.post(
        "/api/packages", json=CREATE_PAYLOAD, headers=super_admin_headers
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


# ── items CRUD ───────────────────────────────────────────────────────────────


async def test_add_and_delete_item(
    client: AsyncClient, super_admin_headers
) -> None:
    created = await client.post(
        "/api/packages", json=CREATE_PAYLOAD, headers=super_admin_headers
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

    detail = await client.get(f"/api/packages/{pid}?include_translations=true")
    types = [i["item_type"] for i in detail.json()["items"]]
    assert "meal" not in types


# ── delete ───────────────────────────────────────────────────────────────────


async def test_delete_package(
    client: AsyncClient, super_admin_headers
) -> None:
    created = await client.post(
        "/api/packages", json=CREATE_PAYLOAD, headers=super_admin_headers
    )
    pid = created.json()["id"]
    resp = await client.delete(f"/api/packages/{pid}", headers=super_admin_headers)
    assert resp.status_code == 204
    get_resp = await client.get(f"/api/packages/{pid}")
    assert get_resp.status_code == 404
