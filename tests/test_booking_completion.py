from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils import today_tashkent
from app.models.booking import Booking, BookingStatus, BookingType
from app.services.booking_service import complete_past_bookings
from tests.factories import make_room, make_sanatorium, make_user


def _booking(user, room, *, check_out_delta: int, status: BookingStatus) -> Booking:
    check_out = today_tashkent() + timedelta(days=check_out_delta)
    return Booking(
        user_id=user.id,
        room_id=room.id,
        booking_type=BookingType.ROOM,
        check_in=check_out - timedelta(days=2),
        check_out=check_out,
        guests=1,
        status=status,
        final_price=Decimal("100"),
        currency="USD",
    )


async def test_complete_past_bookings(db: AsyncSession):
    user = await make_user(db, email="completer@test.com")
    sanatorium = await make_sanatorium(db)
    room = await make_room(db, sanatorium=sanatorium)

    past_confirmed = _booking(
        user, room, check_out_delta=-1, status=BookingStatus.CONFIRMED
    )
    today_confirmed = _booking(
        user, room, check_out_delta=0, status=BookingStatus.CONFIRMED
    )
    future_confirmed = _booking(
        user, room, check_out_delta=3, status=BookingStatus.CONFIRMED
    )
    past_pending = _booking(
        user, room, check_out_delta=-1, status=BookingStatus.PENDING
    )
    past_cancelled = _booking(
        user, room, check_out_delta=-1, status=BookingStatus.CANCELLED
    )
    db.add_all(
        [
            past_confirmed,
            today_confirmed,
            future_confirmed,
            past_pending,
            past_cancelled,
        ]
    )
    await db.commit()

    count = await complete_past_bookings(db)

    assert count == 1
    statuses = {
        booking.id: booking.status
        for booking in (await db.scalars(select(Booking))).all()
    }
    assert statuses[past_confirmed.id] == BookingStatus.COMPLETED
    assert statuses[today_confirmed.id] == BookingStatus.CONFIRMED
    assert statuses[future_confirmed.id] == BookingStatus.CONFIRMED
    assert statuses[past_pending.id] == BookingStatus.PENDING
    assert statuses[past_cancelled.id] == BookingStatus.CANCELLED


async def test_complete_past_bookings_is_idempotent(db: AsyncSession):
    user = await make_user(db, email="completer2@test.com")
    sanatorium = await make_sanatorium(db)
    room = await make_room(db, sanatorium=sanatorium)
    db.add(_booking(user, room, check_out_delta=-5, status=BookingStatus.CONFIRMED))
    await db.commit()

    assert await complete_past_bookings(db) == 1
    assert await complete_past_bookings(db) == 0
