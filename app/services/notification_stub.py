"""Notification stub — inserts DB rows but does not send anything.
Real delivery (email/SMS) requires a payment-success hook and a queue worker;
that's deferred to v0.6.
"""
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification


async def notify_booking_created(db: AsyncSession, booking_id: uuid.UUID) -> None:
    db.add(Notification(booking_id=booking_id, type="booking_created", channel="email"))


async def notify_booking_cancelled(db: AsyncSession, booking_id: uuid.UUID) -> None:
    db.add(Notification(booking_id=booking_id, type="booking_cancelled", channel="email"))
