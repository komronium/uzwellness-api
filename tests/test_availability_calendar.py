from datetime import timedelta
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sanatorium import SanatoriumStatus
from tests.factories import future_date, make_room, make_sanatorium

# Day 0 is a Tuesday far enough out that the booking made below is never in
# the past.
_DAY0 = future_date(1, min_days=60)


def _day(offset: int) -> str:
    return (_DAY0 + timedelta(days=offset)).isoformat()


async def test_admin_availability_calendar_returns_rooms_rate_plans_and_days(
    client: AsyncClient,
    db: AsyncSession,
    admin_user,
    admin_headers,
):
    sanatorium = await make_sanatorium(
        db, status=SanatoriumStatus.APPROVED, admin_user_id=admin_user.id
    )
    room = await make_room(
        db,
        sanatorium=sanatorium,
        name="Standard Double Room",
        inventory_count=4,
        base_price="1000.00",
        base_currency="UZS",
    )
    rate_plan = await client.post(
        "/api/rate-plans",
        headers=admin_headers,
        json={
            "room_id": str(room.id),
            "name": {
                "uz": "Nonushta bilan",
                "ru": "С завтраком",
                "en": "Breakfast Included",
            },
            "board": "breakfast",
            "board_guests": 2,
            "payment_timing": "prepay",
            "confirmation": "instant",
            "price_adjustment_percent": "10.00",
        },
    )
    assert rate_plan.status_code == 201, rate_plan.text
    rate_plan_id = rate_plan.json()["id"]

    resp = await client.get(
        "/api/availability/calendar",
        headers=admin_headers,
        params={
            "sanatorium_id": str(sanatorium.id),
            "from": _day(0),
            "to": _day(3),
            "rate_plan_ids": rate_plan_id,
        },
    )

    assert resp.status_code == 200, resp.text
    room_row = resp.json()["rooms"][0]
    assert room_row["id"] == str(room.id)
    assert len(room_row["days"]) == 3
    assert room_row["days"][0]["room_status"] == "bookable"
    assert room_row["days"][0]["units_available"] == 4
    assert room_row["rate_plans"][0]["id"] == rate_plan_id
    assert Decimal(
        str(room_row["rate_plans"][0]["days"][0]["selling_rate"])
    ) == Decimal("1100.00")


async def test_admin_sets_available_allotment_for_inclusive_date_range(
    client: AsyncClient,
    db: AsyncSession,
    admin_user,
    admin_headers,
):
    sanatorium = await make_sanatorium(
        db, status=SanatoriumStatus.APPROVED, admin_user_id=admin_user.id
    )
    room = await make_room(db, sanatorium=sanatorium, inventory_count=4)

    update = await client.patch(
        f"/api/rooms/{room.id}/availability/allotment",
        headers=admin_headers,
        json={
            "date_from": _day(0),
            "date_to": _day(1),
            "units_available": 2,
        },
    )

    assert update.status_code == 200, update.text
    rows = update.json()
    assert [row["date"] for row in rows] == [_day(0), _day(1)]
    assert all(row["units_available"] == 2 for row in rows)
    assert all(row["units_blocked"] == 2 for row in rows)

    calendar = await client.get(
        "/api/availability/calendar",
        headers=admin_headers,
        params={
            "sanatorium_id": str(sanatorium.id),
            "from": _day(0),
            "to": _day(2),
        },
    )
    assert calendar.status_code == 200, calendar.text
    days = calendar.json()["rooms"][0]["days"]
    assert [day["units_available"] for day in days] == [2, 2]


async def test_bulk_rates_and_status_update_rate_plan_calendar(
    client: AsyncClient,
    db: AsyncSession,
    admin_user,
    admin_headers,
):
    sanatorium = await make_sanatorium(
        db, status=SanatoriumStatus.APPROVED, admin_user_id=admin_user.id
    )
    room = await make_room(db, sanatorium=sanatorium, inventory_count=3)
    rate_plan = await client.post(
        "/api/rate-plans",
        headers=admin_headers,
        json={
            "room_id": str(room.id),
            "name": {"uz": "Oddiy", "ru": "Обычный", "en": "Standard"},
            "board": "breakfast",
        },
    )
    assert rate_plan.status_code == 201, rate_plan.text
    rate_plan_id = rate_plan.json()["id"]

    rates = await client.post(
        "/api/availability/bulk/rates",
        headers=admin_headers,
        json={
            "sanatorium_id": str(sanatorium.id),
            "date_ranges": [{"date_from": _day(0), "date_to": _day(2)}],
            "weekdays": [0, 1, 2, 3, 4, 5, 6],
            "rate_plan_ids": [rate_plan_id],
            "selling_rate": "900.00",
            "weekend_selling_rate": "1200.00",
        },
    )
    assert rates.status_code == 200, rates.text
    assert rates.json()["updated"] == 3

    closed = await client.post(
        "/api/availability/bulk/status",
        headers=admin_headers,
        json={
            "sanatorium_id": str(sanatorium.id),
            "date_ranges": [{"date_from": _day(1), "date_to": _day(1)}],
            "rate_plan_ids": [rate_plan_id],
            "is_closed": True,
        },
    )
    assert closed.status_code == 200, closed.text

    calendar = await client.get(
        "/api/availability/calendar",
        headers=admin_headers,
        params={
            "sanatorium_id": str(sanatorium.id),
            "from": _day(0),
            "to": _day(3),
            "rate_plan_ids": rate_plan_id,
        },
    )
    assert calendar.status_code == 200, calendar.text
    days = calendar.json()["rooms"][0]["rate_plans"][0]["days"]
    assert [day["selling_rate"] for day in days] == ["900.00", "900.00", "900.00"]
    assert days[1]["is_closed"] is True
    assert days[1]["is_sellable"] is False

    logs = await client.get(
        "/api/availability/logs",
        headers=admin_headers,
        params={
            "sanatorium_id": str(sanatorium.id),
            "rate_plan_id": rate_plan_id,
            "category": "rate",
        },
    )
    assert logs.status_code == 200, logs.text
    assert logs.json()["total"] == 1
    log = logs.json()["items"][0]
    assert log["action"] == "bulk_rates"
    assert log["check_in_from"] == _day(0)
    assert log["check_in_to"] == _day(2)
    assert log["after"]["selling_rate"] == "900.00"


async def test_bulk_restrictions_are_enforced_on_booking(
    client: AsyncClient,
    db: AsyncSession,
    admin_user,
    admin_headers,
    customer_headers,
):
    sanatorium = await make_sanatorium(
        db, status=SanatoriumStatus.APPROVED, admin_user_id=admin_user.id
    )
    room = await make_room(db, sanatorium=sanatorium, inventory_count=3)
    rate_plan = await client.post(
        "/api/rate-plans",
        headers=admin_headers,
        json={
            "room_id": str(room.id),
            "name": {"uz": "Oddiy", "ru": "Обычный", "en": "Standard"},
            "board": "breakfast",
        },
    )
    rate_plan_id = rate_plan.json()["id"]

    restrictions = await client.post(
        "/api/availability/bulk/restrictions",
        headers=admin_headers,
        json={
            "sanatorium_id": str(sanatorium.id),
            "date_ranges": [{"date_from": _day(0), "date_to": _day(0)}],
            "rate_plan_ids": [rate_plan_id],
            "min_stay_arrival_nights": 3,
        },
    )
    assert restrictions.status_code == 200, restrictions.text

    booking = await client.post(
        "/api/bookings",
        headers=customer_headers,
        json={
            "room_id": str(room.id),
            "rate_plan_id": rate_plan_id,
            "check_in": _day(0),
            "check_out": _day(2),
            "guests": 1,
        },
    )
    assert booking.status_code == 400


async def test_bulk_copy_rates_uses_existing_rate_values(
    client: AsyncClient,
    db: AsyncSession,
    admin_user,
    admin_headers,
):
    sanatorium = await make_sanatorium(
        db, status=SanatoriumStatus.APPROVED, admin_user_id=admin_user.id
    )
    room = await make_room(db, sanatorium=sanatorium, inventory_count=3)
    rate_plan = await client.post(
        "/api/rate-plans",
        headers=admin_headers,
        json={
            "room_id": str(room.id),
            "name": {"uz": "Oddiy", "ru": "Обычный", "en": "Standard"},
            "board": "breakfast",
        },
    )
    rate_plan_id = rate_plan.json()["id"]
    await client.post(
        "/api/availability/bulk/rates",
        headers=admin_headers,
        json={
            "sanatorium_id": str(sanatorium.id),
            "date_ranges": [{"date_from": _day(0), "date_to": _day(0)}],
            "rate_plan_ids": [rate_plan_id],
            "selling_rate": "777.00",
        },
    )

    copied = await client.post(
        "/api/availability/bulk/copy-rates",
        headers=admin_headers,
        json={
            "sanatorium_id": str(sanatorium.id),
            "source_date_from": _day(0),
            "source_date_to": _day(0),
            "target_date_from": _day(7),
            "target_date_to": _day(7),
            "rate_plan_ids": [rate_plan_id],
            "alignment": "date_order",
            "overwrite_existing": True,
        },
    )
    assert copied.status_code == 200, copied.text
    assert copied.json()["updated"] == 1

    calendar = await client.get(
        "/api/availability/calendar",
        headers=admin_headers,
        params={
            "sanatorium_id": str(sanatorium.id),
            "from": _day(7),
            "to": _day(8),
            "rate_plan_ids": rate_plan_id,
        },
    )
    assert (
        calendar.json()["rooms"][0]["rate_plans"][0]["days"][0]["selling_rate"]
        == "777.00"
    )
