from datetime import date, timedelta
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rate_plan import (
    BoardType,
    ConfirmationType,
    PaymentTiming,
    RatePlan,
)
from tests.factories import make_room, make_sanatorium

_CHECK_IN = (date.today() + timedelta(days=20)).isoformat()
_CHECK_OUT = (date.today() + timedelta(days=22)).isoformat()


async def test_optional_board_is_charged_once(
    client: AsyncClient, db: AsyncSession, customer_headers
) -> None:
    """Board is part of the rate-plan night price; the classic booking flow
    used to add it a second time on top."""
    sanatorium = await make_sanatorium(db)
    room = await make_room(db, sanatorium=sanatorium, base_price="100.00", capacity=2)
    rate_plan = RatePlan(
        room_id=room.id,
        name={"en": "Full board"},
        board=BoardType.FULL_BOARD,
        payment_timing=PaymentTiming.AT_HOTEL,
        confirmation=ConfirmationType.INSTANT,
        board_optional=True,
        board_price=Decimal("10.00"),
        board_guests=2,
    )
    db.add(rate_plan)
    await db.commit()

    resp = await client.post(
        "/api/bookings",
        json={
            "room_id": str(room.id),
            "rate_plan_id": str(rate_plan.id),
            "check_in": _CHECK_IN,
            "check_out": _CHECK_OUT,
            "guests": 2,
        },
        headers=customer_headers,
    )

    assert resp.status_code == 201, resp.text
    # 2 nights x (100 base + 10 board x 2 guests) = 240, not 280
    assert Decimal(resp.json()["final_price"]) == Decimal("240.00")
