from __future__ import annotations

import math
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.notifier import BookingNotifier
from app.core.utils import date_range, pick_locale
from app.models.availability import RoomAvailability
from app.models.booking import Booking, BookingStatus, BookingType
from app.models.notification import Notification
from app.models.package import Package
from app.models.room import Room
from app.models.sanatorium import Sanatorium, SanatoriumStatus
from app.models.user import User, UserRole
from app.schemas.booking import BookingCreate
from app.services.booking_pricing_policy import BookingPricingPolicy
from app.services.email_service import BookingEmailContext

_CENTS = Decimal("0.01")


class PackageBookingFlow:
    """Package booking — the room is fixed at package-creation time.

    The customer just picks a package and a check-in date. The flow:
      1. Resolve package + its assigned room (locked) + sanatorium (approved).
      2. Derive `check_out = check_in + package.duration_nights`. An explicit
         `check_out` from the client must match.
      3. Lock per-night availability rows and decrement units.
      4. `final_price = package.base_price * guests`, snapshot.
    """

    booking_type = BookingType.PACKAGE

    def __init__(
        self,
        db: AsyncSession,
        pricing: BookingPricingPolicy,
        notifier: BookingNotifier,
    ) -> None:
        self.db = db
        self.pricing = pricing
        self.notifier = notifier

    def matches(self, payload: BookingCreate) -> bool:
        return payload.package_id is not None

    async def create(self, payload: BookingCreate, user: User) -> Booking:
        package = await self._load_package(payload.package_id)
        sanatorium = await self._approved_sanatorium(package.sanatorium_id)

        check_out = payload.check_out or (
            payload.check_in + timedelta(days=package.duration_nights)
        )
        expected_out = payload.check_in + timedelta(days=package.duration_nights)
        if check_out != expected_out:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"check_out must equal check_in + {package.duration_nights} "
                    "nights for this package"
                ),
            )
        all_dates = list(date_range(payload.check_in, check_out))

        room = await self._lock_room(package.room_id)
        rooms_count = self._validate_and_compute_rooms(room, payload.guests)
        await self._reserve_units(room, all_dates, rooms_count)

        is_b2b = user.role == UserRole.AGENT
        base_total = (package.base_price * payload.guests).quantize(
            _CENTS, ROUND_HALF_UP
        )
        pricing = await self.pricing.apply(
            base_total=base_total,
            sanatorium=sanatorium,
            user=user,
            is_b2b=is_b2b,
            payload=payload,
        )

        booking = Booking(
            user_id=user.id,
            package_id=package.id,
            room_id=room.id,
            booking_type=BookingType.PACKAGE,
            check_in=payload.check_in,
            check_out=check_out,
            guests=payload.guests,
            rooms_count=rooms_count,
            status=BookingStatus.CONFIRMED,
            final_price=pricing.final_price,
            currency=package.currency,
            is_b2b=is_b2b,
            b2b_client_price=pricing.b2b_client_price,
            guest_details=[g.model_dump() for g in payload.guest_details],
            commission_snapshot=pricing.commission_amount,
            commission_percent_snapshot=pricing.commission_percent,
            agent_discount_percent_snapshot=(
                pricing.agent_discount_percent if is_b2b else None
            ),
        )
        self.db.add(booking)
        await self.db.flush()
        self.db.add(
            Notification(
                booking_id=booking.id, type="booking_created", channel="email"
            )
        )
        await self.db.commit()

        await self._send_received_email(booking, user, pick_locale(sanatorium.name))
        return await self._load(booking.id)

    # ── helpers ────────────────────────────────────────────────────────────

    async def _load_package(self, package_id) -> Package:
        package = await self.db.get(Package, package_id)
        if package is None or not package.is_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Package not found"
            )
        return package

    async def _approved_sanatorium(self, sanatorium_id) -> Sanatorium:
        sanatorium = await self.db.get(Sanatorium, sanatorium_id)
        if sanatorium is None or sanatorium.status != SanatoriumStatus.APPROVED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Sanatorium is not available for booking",
            )
        return sanatorium

    async def _lock_room(self, room_id) -> Room:
        room = await self.db.scalar(
            select(Room).where(Room.id == room_id).with_for_update(of=Room)
        )
        if room is None or not room.is_active:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Package's assigned room is unavailable",
            )
        return room

    @staticmethod
    def _validate_and_compute_rooms(room: Room, guests: int) -> int:
        if room.capacity < 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Room has no capacity",
            )
        rooms_count = math.ceil(guests / room.capacity)
        if rooms_count > room.inventory_count:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Need {rooms_count} room(s) for {guests} guest(s) "
                    f"but only {room.inventory_count} exist"
                ),
            )
        return rooms_count

    async def _reserve_units(
        self, room: Room, dates: list, rooms_count: int
    ) -> None:
        if room.inventory_count < 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Room has no inventory",
            )
        existing = {
            row.date: row
            for row in (
                await self.db.execute(
                    select(RoomAvailability)
                    .where(
                        RoomAvailability.room_id == room.id,
                        RoomAvailability.date.in_(dates),
                    )
                    .with_for_update()
                )
            ).scalars()
        }
        for d in dates:
            row = existing.get(d)
            if row is None:
                row = RoomAvailability(
                    room_id=room.id,
                    date=d,
                    units_blocked=0,
                    units_booked=rooms_count,
                )
                self.db.add(row)
                continue
            if (
                row.units_blocked + row.units_booked + rooms_count
                > room.inventory_count
            ):
                free = room.inventory_count - row.units_blocked - row.units_booked
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Only {max(free, 0)} unit(s) free on {d}, "
                        f"need {rooms_count}"
                    ),
                )
            row.units_booked += rooms_count

    async def _load(self, booking_id) -> Booking:
        stmt = (
            select(Booking)
            .options(
                selectinload(Booking.extra_beds),
                selectinload(Booking.user),
                selectinload(Booking.payments),
            )
            .where(Booking.id == booking_id)
        )
        return (await self.db.execute(stmt)).scalar_one()

    async def _send_received_email(
        self, booking: Booking, user: User, display_name: str
    ) -> None:
        if not user.email:
            return
        ctx = BookingEmailContext(
            booking_code=booking.code,
            sanatorium_name=display_name,
            check_in=booking.check_in,
            check_out=booking.check_out,
            guest_name=user.full_name or user.email,
            total_price=booking.final_price,
            currency=booking.currency,
        )
        self.notifier.booking_received(to=user.email, ctx=ctx)
