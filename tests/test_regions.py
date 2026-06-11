import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.region import Region


async def _make_region(
    db: AsyncSession,
    *,
    slug: str,
    name_en: str,
    is_active: bool = True,
) -> Region:
    r = Region(
        slug=slug,
        name={"en": name_en},
        is_active=is_active,
    )
    db.add(r)
    await db.commit()
    await db.refresh(r)
    return r


# ── create / RBAC ──────────────────────────────────────────────────────────


async def test_super_admin_creates_region(
    client: AsyncClient, super_admin_headers
) -> None:
    payload = {
        "slug": "toshkent",
        "name": {
            "uz": "Toshkent viloyati",
            "ru": "Ташкентская область",
            "en": "Tashkent Region",
        },
    }
    resp = await client.post("/api/regions", json=payload, headers=super_admin_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["slug"] == "toshkent"
    assert body["name"] == payload["name"]
    assert body["is_active"] is True


async def test_customer_cannot_create_region(
    client: AsyncClient, customer_headers
) -> None:
    payload = {"name": {"uz": "x", "ru": "x", "en": "x"}}
    resp = await client.post("/api/regions", json=payload, headers=customer_headers)
    assert resp.status_code == 403


async def test_anonymous_can_list(client: AsyncClient, db: AsyncSession) -> None:
    await _make_region(db, slug="r", name_en="R")
    resp = await client.get("/api/regions")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


async def test_slug_uniqueness_appends_suffix(
    client: AsyncClient, super_admin_headers, db: AsyncSession
) -> None:
    await _make_region(db, slug="samarqand", name_en="Samarkand")
    payload = {
        "name": {"uz": "Samarqand", "ru": "Samarkand", "en": "Samarkand"},
    }
    resp = await client.post("/api/regions", json=payload, headers=super_admin_headers)
    assert resp.status_code == 201
    assert resp.json()["slug"] == "samarqand-2"


# ── list / detail ──────────────────────────────────────────────────────────


async def test_list_resolves_locale(client: AsyncClient, db: AsyncSession) -> None:
    await _make_region(db, slug="r", name_en="Tashkent Region")
    resp = await client.get("/api/regions?lang=en")
    assert resp.json()["items"][0]["name"] == "Tashkent Region"


async def test_include_translations_returns_dicts(
    client: AsyncClient, db: AsyncSession
) -> None:
    await _make_region(db, slug="r", name_en="Tashkent Region")
    resp = await client.get("/api/regions?include_translations=true")
    assert isinstance(resp.json()["items"][0]["name"], dict)


async def test_list_ordered_by_insertion(client: AsyncClient, db: AsyncSession) -> None:
    # No display_order — list is sorted by created_at ASC.
    await _make_region(db, slug="first", name_en="First")
    await _make_region(db, slug="second", name_en="Second")
    resp = await client.get("/api/regions")
    slugs = [r["slug"] for r in resp.json()["items"]]
    assert slugs == ["first", "second"]


async def test_active_only_filter(client: AsyncClient, db: AsyncSession) -> None:
    await _make_region(db, slug="on", name_en="On", is_active=True)
    await _make_region(db, slug="off", name_en="Off", is_active=False)
    resp = await client.get("/api/regions?active_only=true")
    slugs = [r["slug"] for r in resp.json()["items"]]
    assert slugs == ["on"]


async def test_get_by_slug(client: AsyncClient, db: AsyncSession) -> None:
    await _make_region(db, slug="samarqand", name_en="Samarkand")
    resp = await client.get("/api/regions/samarqand?lang=en")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Samarkand"


async def test_get_by_id(client: AsyncClient, db: AsyncSession) -> None:
    r = await _make_region(db, slug="r", name_en="R")
    resp = await client.get(f"/api/regions/{r.id}")
    assert resp.status_code == 200


async def test_unknown_region_404(client: AsyncClient) -> None:
    assert (await client.get("/api/regions/no-such-slug")).status_code == 404


# ── update / delete ────────────────────────────────────────────────────────


async def test_partial_update_merges_translations(
    client: AsyncClient, super_admin_headers, db: AsyncSession
) -> None:
    r = await _make_region(db, slug="r", name_en="Old")
    resp = await client.patch(
        f"/api/regions/{r.id}",
        json={"name": {"uz": "Yangi"}},
        headers=super_admin_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"]["uz"] == "Yangi"
    assert body["name"]["en"] == "Old"


async def test_delete_unknown_region_404(
    client: AsyncClient, super_admin_headers
) -> None:
    resp = await client.delete(
        f"/api/regions/{uuid.uuid4()}", headers=super_admin_headers
    )
    assert resp.status_code == 404
