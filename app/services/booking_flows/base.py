from __future__ import annotations

import math
from typing import Protocol

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.availability import RoomAvailability
from app.models.booking import Booking
from app.models.notification import Notification
from app.models.room import Room
from app.models.sanatorium import Sanatorium, SanatoriumStatus
from app.models.user import User
from app.schemas.booking import BookingCreate
from app.services.booking_pricing_policy import BookingPricingPolicy
from app.services.email_service import BookingEmailContext, send_booking_received


class BookingFlow(Protocol):
    """Each booking type (ROOM, SESSION, PACKAGE…) is its own flow."""

    def matches(self, payload: BookingCreate) -> bool: ...

    async def create(self, payload: BookingCreate, user: User) -> Booking: ...


class BookingFlowBase:
    """Shared state + helpers used by every concrete booking flow."""

    def __init__(
        self,
        db: AsyncSession,
        pricing: BookingPricingPolicy,
    ) -> None:
        self.db = db
        self.pricing = pricing

    async def _approved_sanatorium(self, sanatorium_id) -> Sanatorium:
        sanatorium = await self.db.get(Sanatorium, sanatorium_id)
        if sanatorium is None or sanatorium.status != SanatoriumStatus.APPROVED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Sanatorium is not available for booking",
            )
        return sanatorium

    async def _load(self, booking_id) -> Booking:
        return await self.db.scalar(
            select(Booking)
            .options(
                selectinload(Booking.extra_beds),
                selectinload(Booking.user),
                selectinload(Booking.payments),
            )
            .where(Booking.id == booking_id)
        )

    async def _reserve_units(self, room: Room, dates: list, rooms_count: int) -> None:
        """Lazy-materialize availability rows; bump units_booked by rooms_count.

        409s if any night has fewer than `rooms_count` free units.
        """
        if room.inventory_count < 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Room has no inventory",
            )
        existing = {
            row.date: row
            for row in await self.db.scalars(
                select(RoomAvailability)
                .where(
                    RoomAvailability.room_id == room.id,
                    RoomAvailability.date.in_(dates),
                )
                .with_for_update()
            )
        }
        for d in dates:
            row = existing.get(d)
            if row is None:
                self.db.add(
                    RoomAvailability(
                        room_id=room.id,
                        date=d,
                        units_blocked=0,
                        units_booked=rooms_count,
                    )
                )
                continue
            if (
                row.units_blocked + row.units_booked + rooms_count
                > room.inventory_count
            ):
                free = room.inventory_count - row.units_blocked - row.units_booked
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Only {max(free, 0)} unit(s) free on {d}, need {rooms_count}"
                    ),
                )
            row.units_booked += rooms_count

    @staticmethod
    def _queue_created_notification(booking: Booking) -> Notification:
        return Notification(
            booking_id=booking.id, type="booking_created", channel="email"
        )

    @staticmethod
    def _send_received_email(
        booking: Booking, user: User, sanatorium_name: str
    ) -> None:
        if not user.email:
            return
        send_booking_received(
            to=user.email,
            ctx=BookingEmailContext(
                booking_code=booking.code,
                sanatorium_name=sanatorium_name,
                check_in=booking.check_in,
                check_out=booking.check_out,
                guest_name=user.full_name or user.email,
                total_price=booking.final_price,
                currency=booking.currency,
            ),
        )


def rooms_needed_for(guests: int, capacity: int) -> int:
    """How many same-type rooms fit `guests`, given per-room `capacity`."""
    if capacity < 1:
        return 0
    return math.ceil(guests / capacity)


def rooms_count_for_guests(room: Room, guests: int) -> int:
    """Validate room has usable capacity and return how many units `guests` need."""
    if room.capacity < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Room has no capacity",
        )
    rooms_count = rooms_needed_for(guests, room.capacity)
    if rooms_count > room.inventory_count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Need {rooms_count} room(s) for {guests} guest(s) "
                f"but only {room.inventory_count} exist"
            ),
        )
    return rooms_count
