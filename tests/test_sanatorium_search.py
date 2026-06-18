from datetime import date
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.availability import RoomAvailability
from app.models.region import Region
from app.models.sanatorium import (
    PropertyType,
    Sanatorium,
    SanatoriumImage,
    SanatoriumStatus,
)
from tests.factories import make_room


async def _make_region(db: AsyncSession, *, slug: str, name_en: str) -> Region:
    region = Region(slug=slug, name={"en": name_en, "uz": name_en, "ru": name_en})
    db.add(region)
    await db.commit()
    await db.refresh(region)
    return region


async def _make_sanatorium(
    db: AsyncSession,
    *,
    slug: str,
    name_en: str,
    city: str = "Boysun",
    region: Region | None = None,
    treatment_focuses: list[str] | None = None,
    avg_rating: Decimal | None = None,
    property_type: PropertyType = PropertyType.SANATORIUM,
) -> Sanatorium:
    sanatorium = Sanatorium(
        name={"en": name_en, "uz": name_en, "ru": name_en},
        slug=slug,
        description={},
        city=city,
        region_id=region.id if region else None,
        address={},
        stars=4,
        treatment_focuses=treatment_focuses or [],
        avg_rating=avg_rating,
        review_count=7 if avg_rating is not None else 0,
        status=SanatoriumStatus.APPROVED,
        property_type=property_type,
    )
    db.add(sanatorium)
    await db.commit()
    await db.refresh(sanatorium)
    return sanatorium


async def _add_image(db: AsyncSession, sanatorium: Sanatorium, *, url: str) -> None:
    image = SanatoriumImage(
        sanatorium_id=sanatorium.id,
        url=url,
        order=0,
        is_primary=True,
    )
    db.add(image)
    await db.commit()


async def test_sanatorium_search_matches_location_and_returns_cheapest_room(
    client: AsyncClient, db: AsyncSession
) -> None:
    region = await _make_region(db, slug="surxondaryo", name_en="Surxondaryo")
    sanatorium = await _make_sanatorium(
        db,
        slug="boysun-spa",
        name_en="Boysun Spa",
        region=region,
        avg_rating=Decimal("4.70"),
    )
    await _add_image(db, sanatorium, url="https://cdn.test/boysun.jpg")
    await make_room(db, sanatorium=sanatorium, name="Suite", base_price="150.00")
    cheap_room = await make_room(
        db, sanatorium=sanatorium, name="Standard", base_price="90.00"
    )

    resp = await client.get(
        "/api/sanatoriums/search",
        params={
            "location": "Boysun",
            "check_in": "2026-10-02",
            "check_out": "2026-10-04",
            "adults": 2,
        },
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["sanatorium_slug"] == "boysun-spa"
    assert item["region_name"] == "Surxondaryo"
    assert item["primary_image_url"] == "https://cdn.test/boysun.jpg"
    assert item["available_room_id"] == str(cheap_room.id)
    assert item["available_room_name"] == "Standard"
    assert item["nights"] == 2
    assert item["min_total_price"] == "180.00"
    assert item["min_total_price_usd"] == "180.00"


async def test_sanatorium_search_filters_by_treatment_focus(
    client: AsyncClient, db: AsyncSession
) -> None:
    matching = await _make_sanatorium(
        db,
        slug="cardio-resort",
        name_en="Cardio Resort",
        treatment_focuses=["cardiology"],
    )
    non_matching = await _make_sanatorium(
        db,
        slug="detox-resort",
        name_en="Detox Resort",
        treatment_focuses=["detox"],
    )
    await make_room(db, sanatorium=matching)
    await make_room(db, sanatorium=non_matching)

    resp = await client.get(
        "/api/sanatoriums/search",
        params={
            "check_in": "2026-10-02",
            "check_out": "2026-10-05",
            "treatment_focus": "cardiology",
        },
    )

    assert resp.status_code == 200, resp.text
    slugs = [item["sanatorium_slug"] for item in resp.json()["items"]]
    assert slugs == ["cardio-resort"]


async def test_sanatorium_search_excludes_unavailable_rooms(
    client: AsyncClient, db: AsyncSession
) -> None:
    sanatorium = await _make_sanatorium(
        db, slug="fully-blocked", name_en="Fully Blocked"
    )
    room = await make_room(db, sanatorium=sanatorium, inventory_count=1)
    db.add(
        RoomAvailability(
            room_id=room.id,
            date=date(2026, 10, 3),
            units_blocked=1,
            units_booked=0,
        )
    )
    await db.commit()

    resp = await client.get(
        "/api/sanatoriums/search",
        params={
            "check_in": "2026-10-02",
            "check_out": "2026-10-05",
            "adults": 2,
        },
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["total"] == 0


async def test_sanatorium_search_counts_children_as_guests(
    client: AsyncClient, db: AsyncSession
) -> None:
    sanatorium = await _make_sanatorium(db, slug="family", name_en="Family")
    await make_room(db, sanatorium=sanatorium, capacity=2, inventory_count=2)

    resp = await client.get(
        "/api/sanatoriums/search",
        params={
            "check_in": "2026-10-02",
            "check_out": "2026-10-05",
            "adults": 2,
            "children": 1,
        },
    )

    assert resp.status_code == 200, resp.text
    item = resp.json()["items"][0]
    assert item["guests"] == 3
    assert item["rooms_count_needed"] == 2
    assert item["min_total_price"] == "600.00"


async def test_sanatorium_search_rejects_invalid_date_range(
    client: AsyncClient,
) -> None:
    resp = await client.get(
        "/api/sanatoriums/search",
        params={
            "check_in": "2026-10-05",
            "check_out": "2026-10-02",
        },
    )

    assert resp.status_code == 400
    assert resp.json()["detail"] == "check_out must be after check_in"


async def test_sanatorium_search_filters_by_property_type(
    client: AsyncClient, db: AsyncSession
) -> None:
    sanatorium = await _make_sanatorium(
        db, slug="medical-resort", name_en="Medical Resort"
    )
    wellness = await _make_sanatorium(
        db,
        slug="zen-retreat",
        name_en="Zen Retreat",
        property_type=PropertyType.WELLNESS,
    )
    await make_room(db, sanatorium=sanatorium, name="Standard", base_price="100.00")
    await make_room(db, sanatorium=wellness, name="Studio", base_price="80.00")

    base_params = {"check_in": "2026-10-02", "check_out": "2026-10-04", "adults": 2}

    resp = await client.get(
        "/api/sanatoriums/search",
        params={**base_params, "property_type": "wellness"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["sanatorium_slug"] == "zen-retreat"

    resp = await client.get(
        "/api/sanatoriums/search",
        params={**base_params, "property_type": "sanatorium"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["sanatorium_slug"] == "medical-resort"

    resp = await client.get("/api/sanatoriums/search", params=base_params)
    assert resp.json()["total"] == 2
