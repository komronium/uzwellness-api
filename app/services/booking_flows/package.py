from __future__ import annotations

from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException, status
from sqlalchemy import select

from app.core.utils import date_range, pick_locale
from app.models.booking import Booking, BookingStatus, BookingType
from app.models.package import Package
from app.models.room import Room
from app.models.user import User, UserRole
from app.schemas.booking import BookingCreate
from app.services.booking_flows.base import BookingFlowBase, rooms_count_for_guests

_CENTS = Decimal("0.01")


class PackageBookingFlow(BookingFlowBase):
    booking_type = BookingType.PACKAGE

    def matches(self, payload: BookingCreate) -> bool:
        return payload.package_id is not None

    async def create(self, payload: BookingCreate, user: User) -> Booking:
        package = await self._load_package(payload.package_id)
        sanatorium = await self._approved_sanatorium(package.sanatorium_id)
        check_out = self._check_out(payload, package)
        room = await self._lock_room(package.room_id)
        rooms_count = rooms_count_for_guests(room, payload.guests)
        all_dates = list(date_range(payload.check_in, check_out))
        await self._reserve_units(room, all_dates, rooms_count)

        is_b2b = user.role == UserRole.AGENT
        pricing = await self.pricing.apply(
            base_total=self._base_total(package, payload.guests),
            sanatorium=sanatorium,
            user=user,
            is_b2b=is_b2b,
        )
        booking = self._build_booking(
            payload,
            package=package,
            room=room,
            check_out=check_out,
            rooms_count=rooms_count,
            pricing=pricing,
            is_b2b=is_b2b,
            user=user,
        )
        self.db.add(booking)
        await self.db.flush()
        self.db.add(self._queue_created_notification(booking))
        await self.db.commit()

        self._send_received_email(booking, user, pick_locale(sanatorium.name))
        return await self._load(booking.id)

    async def _load_package(self, package_id) -> Package:
        package = await self.db.get(Package, package_id)
        if package is None or not package.is_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Package not found"
            )
        return package

    @staticmethod
    def _check_out(payload: BookingCreate, package: Package):
        expected = payload.check_in + timedelta(days=package.duration_nights)
        check_out = payload.check_out or expected
        if check_out != expected:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"check_out must equal check_in + {package.duration_nights} "
                    "nights for this package"
                ),
            )
        return check_out

    @staticmethod
    def _base_total(package: Package, guests: int) -> Decimal:
        return (package.base_price * guests).quantize(_CENTS, ROUND_HALF_UP)

    @staticmethod
    def _build_booking(
        payload: BookingCreate,
        *,
        package: Package,
        room: Room,
        check_out,
        rooms_count: int,
        pricing,
        is_b2b: bool,
        user: User,
    ) -> Booking:
        return Booking(
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
            guest_details=[g.model_dump() for g in payload.guest_details],
            special_requests=payload.special_requests,
            commission_snapshot=pricing.commission_amount,
            commission_percent_snapshot=pricing.commission_percent,
            agent_discount_percent_snapshot=(
                pricing.agent_discount_percent if is_b2b else None
            ),
        )

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
