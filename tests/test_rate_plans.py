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


async def test_admin_rate_plan_directory_lists_sanatorium_rate_plans(
    client: AsyncClient, db: AsyncSession, admin_user, admin_headers
) -> None:
    sanatorium = await make_sanatorium(db, admin_user_id=admin_user.id)
    standard = await make_room(db, sanatorium=sanatorium, name="Standard Double")
    suite = await make_room(db, sanatorium=sanatorium, name="Family Suite")

    active = await client.post(
        "/api/rate-plans",
        headers=admin_headers,
        json={
            "room_id": str(standard.id),
            "name": {
                "uz": "Nonushta bilan",
                "ru": "С завтраком",
                "en": "Breakfast Included",
            },
            "board": "breakfast",
            "board_guests": 1,
            "payment_timing": "prepay",
            "min_nights": 2,
        },
    )
    inactive = await client.post(
        "/api/rate-plans",
        headers=admin_headers,
        json={
            "room_id": str(suite.id),
            "name": {"uz": "Moslashuvchan", "ru": "Гибкий", "en": "Flexible"},
            "board": "room_only",
        },
    )
    assert active.status_code == 201, active.text
    assert inactive.status_code == 201, inactive.text

    inactive_id = inactive.json()["id"]
    disabled = await client.patch(
        f"/api/rate-plans/{inactive_id}",
        headers=admin_headers,
        json={"is_active": False},
    )
    assert disabled.status_code == 200, disabled.text

    listed = await client.get(
        f"/api/rate-plans?sanatorium_id={sanatorium.id}",
        headers=admin_headers,
    )

    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["total"] == 2
    assert {item["id"] for item in body["items"]} == {
        active.json()["id"],
        inactive_id,
    }
    item = next(row for row in body["items"] if row["id"] == active.json()["id"])
    assert item["room"]["id"] == str(standard.id)
    assert item["meals_summary"] == "1 x breakfast per guest (included)"
    assert item["restrictions_summary"] == "min 2 night(s)"
    assert item["rate_status_summary"] == "Set in calendar"
    assert item["status"] == "active"

    hidden = await client.get(
        f"/api/rate-plans?sanatorium_id={sanatorium.id}&hide_inactive=true",
        headers=admin_headers,
    )
    assert hidden.status_code == 200, hidden.text
    assert hidden.json()["total"] == 1

    filtered = await client.get(
        f"/api/rate-plans?sanatorium_id={sanatorium.id}&room_id={suite.id}",
        headers=admin_headers,
    )
    assert filtered.status_code == 200, filtered.text
    assert filtered.json()["total"] == 1
    assert filtered.json()["items"][0]["id"] == inactive_id


async def test_rate_plan_cancellation_policy_update_is_logged(
    client: AsyncClient, db: AsyncSession, admin_user, admin_headers
) -> None:
    sanatorium = await make_sanatorium(db, admin_user_id=admin_user.id)
    room = await make_room(db, sanatorium=sanatorium)

    created = await client.post(
        "/api/rate-plans",
        headers=admin_headers,
        json={
            "room_id": str(room.id),
            "name": {"uz": "Oddiy", "ru": "Обычный", "en": "Standard"},
            "board": "room_only",
        },
    )
    assert created.status_code == 201, created.text
    rate_plan_id = created.json()["id"]

    updated = await client.patch(
        f"/api/rate-plans/{rate_plan_id}",
        headers=admin_headers,
        json={"refundable": False, "cancellation_penalty_percent": "100.00"},
    )
    assert updated.status_code == 200, updated.text

    logs = await client.get(
        "/api/availability/logs",
        headers=admin_headers,
        params={
            "sanatorium_id": str(sanatorium.id),
            "rate_plan_id": rate_plan_id,
            "category": "cancellation_policy",
        },
    )
    assert logs.status_code == 200, logs.text
    body = logs.json()
    assert body["total"] == 1
    assert body["items"][0]["action"] == "update_cancellation_policy"
    assert body["items"][0]["before"]["refundable"] is True
    assert body["items"][0]["after"]["refundable"] is False


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
