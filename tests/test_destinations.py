import uuid
from datetime import datetime, timezone
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.destination import Destination
from app.models.exchange_rate import ExchangeRate
from app.models.region import Region
from app.models.room import Room
from app.models.sanatorium import Sanatorium, SanatoriumStatus


async def _make_destination(
    db: AsyncSession,
    *,
    slug: str,
    name_en: str,
    tagline_en: str = "tagline",
    is_active: bool = True,
) -> Destination:
    d = Destination(
        slug=slug,
        name={"en": name_en},
        tagline={"en": tagline_en},
        is_active=is_active,
    )
    db.add(d)
    await db.commit()
    await db.refresh(d)
    return d


async def _make_region(
    db: AsyncSession, *, slug: str, name_en: str
) -> Region:
    r = Region(slug=slug, name={"en": name_en})
    db.add(r)
    await db.commit()
    await db.refresh(r)
    return r


async def _make_sanatorium(
    db: AsyncSession,
    *,
    slug: str,
    destination_id: uuid.UUID | None = None,
    region_id: uuid.UUID | None = None,
    status: SanatoriumStatus = SanatoriumStatus.APPROVED,
) -> Sanatorium:
    s = Sanatorium(
        name={"en": slug},
        slug=slug,
        description={},
        city="City",
        region_id=region_id,
        destination_id=destination_id,
        address={},
        stars=4,
        status=status,
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return s


async def _make_room(
    db: AsyncSession,
    *,
    sanatorium_id: uuid.UUID,
    base_price: Decimal,
    base_currency: str = "USD",
) -> Room:
    r = Room(
        sanatorium_id=sanatorium_id,
        name={"en": "Room"},
        capacity=2,
        inventory_count=1,
        base_price=base_price,
        base_currency=base_currency,
        markup_percent=Decimal("0"),
        min_nights=1,
        is_active=True,
    )
    db.add(r)
    await db.commit()
    await db.refresh(r)
    return r


# ── create / RBAC ──────────────────────────────────────────────────────────


async def test_super_admin_creates_destination(
    client: AsyncClient, super_admin_headers
) -> None:
    payload = {
        "slug": "chimgan-mountains",
        "name": {
            "uz": "Chimgan tog'lari",
            "ru": "Чимганские горы",
            "en": "Chimgan Mountains",
        },
        "tagline": {
            "uz": "Alp havosi",
            "ru": "Альпийский воздух",
            "en": "Alpine air",
        },
    }
    resp = await client.post(
        "/api/destinations", json=payload, headers=super_admin_headers
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["slug"] == "chimgan-mountains"
    assert body["tagline"]["en"] == "Alpine air"


async def test_customer_cannot_create_destination(
    client: AsyncClient, customer_headers
) -> None:
    payload = {
        "name": {"uz": "x", "ru": "x", "en": "x"},
        "tagline": {"uz": "y", "ru": "y", "en": "y"},
    }
    resp = await client.post(
        "/api/destinations", json=payload, headers=customer_headers
    )
    assert resp.status_code == 403


# ── list / detail ──────────────────────────────────────────────────────────


async def test_anonymous_can_list(client: AsyncClient, db: AsyncSession) -> None:
    await _make_destination(db, slug="d", name_en="D")
    resp = await client.get("/api/destinations")
    assert resp.json()["total"] == 1


async def test_get_by_slug(client: AsyncClient, db: AsyncSession) -> None:
    await _make_destination(db, slug="chimgan", name_en="Chimgan Mountains")
    resp = await client.get("/api/destinations/chimgan?lang=en")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Chimgan Mountains"


async def test_unknown_destination_404(client: AsyncClient) -> None:
    assert (await client.get("/api/destinations/no-such")).status_code == 404


# ── tiles aggregation ──────────────────────────────────────────────────────


async def test_tiles_count_and_min_price(
    client: AsyncClient, db: AsyncSession
) -> None:
    db.add(
        ExchangeRate(
            pair="USD_UZS",
            rate=Decimal("12500"),
            valid_from=datetime.now(tz=timezone.utc),
        )
    )
    await db.commit()

    d1 = await _make_destination(db, slug="d1", name_en="D1")
    d2 = await _make_destination(db, slug="d2", name_en="D2")

    s1 = await _make_sanatorium(db, slug="s1", destination_id=d1.id)
    s2 = await _make_sanatorium(db, slug="s2", destination_id=d1.id)
    await _make_room(db, sanatorium_id=s1.id, base_price=Decimal("120.00"))
    await _make_room(db, sanatorium_id=s2.id, base_price=Decimal("80.00"))
    # UZS room normalizes to ~$48 — wins the min.
    await _make_room(
        db,
        sanatorium_id=s2.id,
        base_price=Decimal("600000"),
        base_currency="UZS",
    )

    resp = await client.get("/api/destinations/tiles")
    assert resp.status_code == 200, resp.text
    tiles = {t["slug"]: t for t in resp.json()["items"]}
    assert tiles["d1"]["sanatoriums_count"] == 2
    assert Decimal(tiles["d1"]["min_price_usd"]) == Decimal("48")
    assert tiles["d2"]["sanatoriums_count"] == 0
    assert tiles["d2"]["min_price_usd"] is None


async def test_tiles_min_price_applies_markup_and_discount(
    client: AsyncClient, db: AsyncSession
) -> None:
    # Customer price = base * (1 + markup/100) * (1 - discount/100)
    # 100 * 1.10 * 0.90 = 99.00 — that's what the tile must show.
    d = await _make_destination(db, slug="dp", name_en="DP")
    s = await _make_sanatorium(db, slug="sp", destination_id=d.id)
    room = Room(
        sanatorium_id=s.id,
        name={"en": "R"},
        capacity=2,
        inventory_count=1,
        base_price=Decimal("100.00"),
        base_currency="USD",
        markup_percent=Decimal("10"),
        discount_percent=Decimal("10"),
        min_nights=1,
        is_active=True,
    )
    db.add(room)
    await db.commit()

    resp = await client.get("/api/destinations/tiles")
    tile = resp.json()["items"][0]
    assert Decimal(tile["min_price_usd"]).quantize(Decimal("0.01")) == Decimal("99.00")


async def test_tiles_excludes_pending_sanatoriums(
    client: AsyncClient, db: AsyncSession
) -> None:
    d = await _make_destination(db, slug="d", name_en="D")
    s = await _make_sanatorium(
        db, slug="pending", destination_id=d.id, status=SanatoriumStatus.PENDING
    )
    await _make_room(db, sanatorium_id=s.id, base_price=Decimal("999"))
    tile = (await client.get("/api/destinations/tiles")).json()["items"][0]
    assert tile["sanatoriums_count"] == 0
    assert tile["min_price_usd"] is None


async def test_tiles_skips_inactive_destinations(
    client: AsyncClient, db: AsyncSession
) -> None:
    await _make_destination(db, slug="off", name_en="Off", is_active=False)
    await _make_destination(db, slug="on", name_en="On", is_active=True)
    resp = await client.get("/api/destinations/tiles")
    slugs = [t["slug"] for t in resp.json()["items"]]
    assert slugs == ["on"]


# ── update / delete ────────────────────────────────────────────────────────


async def test_partial_update_merges_tagline(
    client: AsyncClient, super_admin_headers, db: AsyncSession
) -> None:
    d = await _make_destination(db, slug="d", name_en="D", tagline_en="Old")
    resp = await client.patch(
        f"/api/destinations/{d.id}",
        json={"tagline": {"uz": "Yangi"}},
        headers=super_admin_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["tagline"]["uz"] == "Yangi"
    assert body["tagline"]["en"] == "Old"


async def test_delete_sets_sanatorium_destination_id_null(
    client: AsyncClient, super_admin_headers, db: AsyncSession
) -> None:
    d = await _make_destination(db, slug="doomed", name_en="Doomed")
    s = await _make_sanatorium(db, slug="s", destination_id=d.id)
    resp = await client.delete(
        f"/api/destinations/{d.id}", headers=super_admin_headers
    )
    assert resp.status_code == 204
    await db.refresh(s)
    assert s.destination_id is None


# ── sanatorium FKs ─────────────────────────────────────────────────────────


async def test_sanatorium_filters_by_destination_id(
    client: AsyncClient, db: AsyncSession
) -> None:
    d1 = await _make_destination(db, slug="d1", name_en="D1")
    d2 = await _make_destination(db, slug="d2", name_en="D2")
    await _make_sanatorium(db, slug="s-d1", destination_id=d1.id)
    await _make_sanatorium(db, slug="s-d2", destination_id=d2.id)
    await _make_sanatorium(db, slug="s-orphan")

    resp = await client.get(f"/api/sanatoriums?destination_id={d1.id}")
    slugs = [s["slug"] for s in resp.json()["items"]]
    assert slugs == ["s-d1"]


async def test_sanatorium_read_includes_nested_region_and_destination(
    client: AsyncClient, db: AsyncSession
) -> None:
    r = await _make_region(db, slug="toshkent", name_en="Tashkent Region")
    d = await _make_destination(db, slug="chimgan", name_en="Chimgan")
    s = await _make_sanatorium(
        db, slug="s", region_id=r.id, destination_id=d.id
    )
    resp = await client.get(f"/api/sanatoriums/{s.id}?lang=en")
    body = resp.json()
    assert body["region_id"] == str(r.id)
    assert body["region"]["slug"] == "toshkent"
    assert body["region"]["name"] == "Tashkent Region"
    assert body["destination_id"] == str(d.id)
    assert body["destination"]["slug"] == "chimgan"
    assert body["destination"]["name"] == "Chimgan"
