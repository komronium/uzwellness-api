import uuid
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.amenity import Amenity
from tests.factories import make_room, make_sanatorium


async def _amenity(db: AsyncSession, name: str) -> Amenity:
    amenity = Amenity(
        name={"uz": name, "ru": name, "en": name},
        description={"uz": "", "ru": "", "en": ""},
        category="rate_plan",
        icon="check",
    )
    db.add(amenity)
    await db.commit()
    await db.refresh(amenity)
    return amenity


async def test_rate_plan_has_own_amenities(
    client: AsyncClient, db: AsyncSession, admin_user, admin_headers
) -> None:
    sanatorium = await make_sanatorium(db, admin_user_id=admin_user.id)
    room = await make_room(db, sanatorium=sanatorium)
    breakfast = await _amenity(db, "Breakfast")
    spa = await _amenity(db, "Spa access")

    created = await client.post(
        "/api/rate-plans",
        headers=admin_headers,
        json={
            "room_id": str(room.id),
            "name": {"uz": "Moslashuvchan", "ru": "Гибкий", "en": "Flexible"},
            "board": "breakfast",
            "amenity_ids": [str(breakfast.id)],
        },
    )

    assert created.status_code == 201, created.text
    body = created.json()
    assert [item["id"] for item in body["amenities"]] == [str(breakfast.id)]

    updated = await client.patch(
        f"/api/rate-plans/{body['id']}",
        headers=admin_headers,
        json={"amenity_ids": [str(spa.id)]},
    )

    assert updated.status_code == 200, updated.text
    assert [item["id"] for item in updated.json()["amenities"]] == [str(spa.id)]

    public = await client.get(f"/api/rate-plans/{body['id']}?lang=en")
    assert public.status_code == 200
    assert public.json()["amenities"][0]["name"] == "Spa access"


async def test_rate_plan_rejects_unknown_amenity(
    client: AsyncClient, db: AsyncSession, admin_user, admin_headers
) -> None:
    sanatorium = await make_sanatorium(db, admin_user_id=admin_user.id)
    room = await make_room(db, sanatorium=sanatorium)

    resp = await client.post(
        "/api/rate-plans",
        headers=admin_headers,
        json={
            "room_id": str(room.id),
            "name": {"uz": "Oddiy", "ru": "Обычный", "en": "Standard"},
            "board": "room_only",
            "amenity_ids": [str(uuid.uuid4())],
        },
    )

    assert resp.status_code == 400


def test_weekend_days_are_friday_and_saturday() -> None:
    from datetime import date
    from types import SimpleNamespace

    from app.core.pricing import calculate_stay_total

    room = SimpleNamespace(
        base_price=Decimal("100.00"),
        base_price_weekend=Decimal("150.00"),
        markup_percent=Decimal("0"),
        discount_percent=None,
    )

    total = calculate_stay_total(
        room,
        [
            date(2026, 5, 29),
            date(2026, 5, 30),
            date(2026, 5, 31),
        ],
    )

    assert total == Decimal("400.00")
