"""Shared helper for resources that attach to a booking."""

import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking
from app.models.user import User, UserRole


async def resolve_owner_for_booking(
    db: AsyncSession,
    *,
    booking_id: uuid.UUID | None,
    actor: User,
    resource_label: str,
) -> uuid.UUID:
    """Return the user_id to record as the owner of a booking-attached row.

    For super_admin attaching on behalf of a customer, the row belongs to the
    booking's customer. Any other actor must own the booking themselves.
    Returns `actor.id` when no booking is attached.
    """
    if booking_id is None:
        return actor.id

    booking = await db.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Booking not found",
        )

    if actor.role == UserRole.SUPER_ADMIN:
        return booking.user_id or actor.id

    if booking.user_id != actor.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Cannot attach a {resource_label} to someone else's booking",
        )
    return actor.id
