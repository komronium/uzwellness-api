from __future__ import annotations

from fastapi import HTTPException, status
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
    # Eight collisions in a row on a 16-digit number means the generator or the
    # table is in a state we should not silently book against. Answer with a
    # retry the guest can act on rather than a 500 they cannot.
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=(
            "We could not assign a reservation number just now. "
            "Please try booking again in a moment."
        ),
    )
