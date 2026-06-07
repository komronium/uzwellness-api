from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking, BookingType, generate_reservation_number


async def next_reservation_number(
    db: AsyncSession, *, booking_type: BookingType, is_b2b: bool
) -> str:
    for _ in range(8):
        reservation_number = generate_reservation_number(
            booking_type=booking_type,
            is_b2b=is_b2b,
        )
        exists = await db.scalar(
            select(Booking.id).where(Booking.reservation_number == reservation_number)
        )
        if exists is None:
            return reservation_number
    raise RuntimeError("Could not generate a unique reservation number")
