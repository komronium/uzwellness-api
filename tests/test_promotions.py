from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import make_room, make_sanatorium


async def _rate_plan(client: AsyncClient, room_id, admin_headers) -> str:
    created = await client.post(
        "/api/rate-plans",
        headers=admin_headers,
        json={
            "room_id": str(room_id),
            "name": {"uz": "Nonushta", "ru": "Завтрак", "en": "Breakfast Included"},
            "board": "breakfast",
            "payment_timing": "prepay",
        },
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


async def test_create_list_detail_and_actions_for_promotion(
    client: AsyncClient, db: AsyncSession, admin_user, admin_headers
) -> None:
    sanatorium = await make_sanatorium(db, admin_user_id=admin_user.id)
    room = await make_room(db, sanatorium=sanatorium)
    rate_plan_id = await _rate_plan(client, room.id, admin_headers)

    created = await client.post(
        "/api/promotions",
        headers=admin_headers,
        json={
            "sanatorium_id": str(sanatorium.id),
            "name": {
                "uz": "10% mobil tarif",
                "ru": "10% мобильный тариф",
                "en": "10% off - Mobile Rate",
            },
            "category": "mobile_rate",
            "discount_percent": "10.00",
            "booking_date_from": "2026-11-06",
            "stay_date_from": "2026-11-06",
            "rate_plan_ids": [rate_plan_id],
        },
    )
    assert created.status_code == 201, created.text
    promotion_id = created.json()["id"]
    assert created.json()["rate_plans"][0]["id"] == rate_plan_id
    assert created.json()["stats"]["reservations"] == 0

    listed = await client.get(
        f"/api/promotions?sanatorium_id={sanatorium.id}&status=active&category=mobile_rate",
        headers=admin_headers,
    )
    assert listed.status_code == 200, listed.text
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["name"] == "10% off - Mobile Rate"

    paused = await client.post(
        f"/api/promotions/{promotion_id}/pause",
        headers=admin_headers,
    )
    assert paused.status_code == 200, paused.text
    assert paused.json()["status"] == "paused"

    duplicated = await client.post(
        f"/api/promotions/{promotion_id}/duplicate",
        headers=admin_headers,
    )
    assert duplicated.status_code == 201, duplicated.text
    assert duplicated.json()["status"] == "paused"
    assert duplicated.json()["name"].endswith("Copy")

    deactivated = await client.post(
        f"/api/promotions/{promotion_id}/deactivate",
        headers=admin_headers,
    )
    assert deactivated.status_code == 200, deactivated.text
    assert deactivated.json()["status"] == "inactive"


async def test_promotion_rejects_rate_plan_from_other_sanatorium(
    client: AsyncClient, db: AsyncSession, admin_user, admin_headers
) -> None:
    own = await make_sanatorium(db, admin_user_id=admin_user.id, slug="own")
    other = await make_sanatorium(db, admin_user_id=admin_user.id, slug="other")
    other_room = await make_room(db, sanatorium=other)
    other_rate_plan_id = await _rate_plan(client, other_room.id, admin_headers)

    created = await client.post(
        "/api/promotions",
        headers=admin_headers,
        json={
            "sanatorium_id": str(own.id),
            "name": {"uz": "Aksiya", "ru": "Акция", "en": "Promo"},
            "category": "custom",
            "discount_percent": "5.00",
            "rate_plan_ids": [other_rate_plan_id],
        },
    )

    assert created.status_code == 400
