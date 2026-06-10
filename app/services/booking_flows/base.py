from __future__ import annotations

import math
from typing import Protocol

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.booking import Booking
from app.models.notification import Notification
from app.models.room import Room
from app.models.sanatorium import Sanatorium
from app.models.user import User
from app.schemas.booking import BookingCreate
from app.services.booking_guards import (
    ROOM_UNAVAILABLE_DETAIL,
    approved_sanatorium,
    lock_room,
    reserve_units,
)
from app.services.booking_pricing_policy import BookingPricingPolicy
from app.services.email_service import BookingEmailContext, send_booking_received
from app.services.reservation_numbers import next_reservation_number


class BookingFlow(Protocol):
    def matches(self, payload: BookingCreate) -> bool: ...

    async def create(self, payload: BookingCreate, user: User) -> Booking: ...


class BookingFlowBase:
    def __init__(
        self,
        db: AsyncSession,
        pricing: BookingPricingPolicy,
    ) -> None:
        self.db = db
        self.pricing = pricing

    async def _approved_sanatorium(self, sanatorium_id) -> Sanatorium:
        return await approved_sanatorium(self.db, sanatorium_id)

    async def _lock_room(
        self,
        room_id,
        *,
        load_price_periods: bool = False,
        detail: str = ROOM_UNAVAILABLE_DETAIL,
    ) -> Room:
        return await lock_room(
            self.db, room_id, load_price_periods=load_price_periods, detail=detail
        )

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
        await reserve_units(self.db, room, dates=dates, rooms_count=rooms_count)

    @staticmethod
    def _queue_created_notification(booking: Booking) -> Notification:
        return Notification(
            booking_id=booking.id, type="booking_created", channel="email"
        )

    async def _assign_reservation_number(self, booking: Booking) -> None:
        booking.reservation_number = await next_reservation_number(
            self.db,
            booking_type=booking.booking_type,
            is_b2b=booking.is_b2b,
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
    if capacity < 1:
        return 0
    return math.ceil(guests / capacity)


def rooms_count_for_guests(room: Room, guests: int) -> int:
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
