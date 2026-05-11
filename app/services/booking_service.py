import uuid
from collections.abc import Sequence
from datetime import date, timedelta

from fastapi import Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.availability import RoomAvailability
from app.models.booking import Booking, BookingStatus
from app.models.room import RoomCategory
from app.models.sanatorium import Sanatorium, SanatoriumStatus
from app.models.user import User, UserRole
from app.schemas.booking import BookingCreate
from app.services.notification_stub import notify_booking_cancelled, notify_booking_created
from app.services.pricing import calculate_final_price

_CANCELLABLE = {BookingStatus.PENDING, BookingStatus.CONFIRMED}


class BookingService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── create ─────────────────────────────────────────────────────────────

    async def create(self, payload: BookingCreate, user: User) -> Booking:
        today = date.today()
        if payload.check_in < today:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="check_in must be today or in the future",
            )
        if payload.check_out <= payload.check_in:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="check_out must be after check_in",
            )

        nights = (payload.check_out - payload.check_in).days
        all_dates = [payload.check_in + timedelta(days=i) for i in range(nights)]

        # Lock the room row first to prevent races on markup/price reads
        room = (
            await self.db.execute(
                select(RoomCategory)
                .where(RoomCategory.id == payload.room_category_id)
                .with_for_update()
            )
        ).scalar_one_or_none()

        if room is None or not room.is_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Room not found"
            )

        sanatorium = (
            await self.db.execute(
                select(Sanatorium).where(Sanatorium.id == room.sanatorium_id)
            )
        ).scalar_one_or_none()
        if sanatorium is None or sanatorium.status != SanatoriumStatus.APPROVED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Sanatorium is not available for booking",
            )

        if nights < room.min_nights:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Minimum stay is {room.min_nights} night(s)",
            )
        if room.capacity < payload.guests:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Room capacity is {room.capacity} guest(s)",
            )

        # Lock availability rows for all dates atomically
        avail_rows = list(
            (
                await self.db.execute(
                    select(RoomAvailability)
                    .where(
                        RoomAvailability.room_category_id == room.id,
                        RoomAvailability.date.in_(all_dates),
                    )
                    .with_for_update()
                )
            ).scalars()
        )

        if len(avail_rows) != nights:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Not all dates are available",
            )

        for row in avail_rows:
            if row.units_available < 1:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"No units available on {row.date}",
                )

        for row in avail_rows:
            row.units_available -= 1

        final_price = calculate_final_price(room.base_price, room.markup_percent)

        booking = Booking(
            user_id=user.id,
            room_category_id=room.id,
            check_in=payload.check_in,
            check_out=payload.check_out,
            guests=payload.guests,
            # Auto-confirm for MVP — real flow requires payment success first
            status=BookingStatus.CONFIRMED,
            final_price=final_price,
            currency=room.base_currency,
        )
        self.db.add(booking)
        await self.db.flush()  # assigns booking.id before notification insert

        await notify_booking_created(self.db, booking.id)
        await self.db.commit()
        await self.db.refresh(booking)
        return booking

    # ── list / get ─────────────────────────────────────────────────────────

    async def list_for_user(
        self,
        user: User,
        *,
        limit: int,
        offset: int,
    ) -> tuple[Sequence[Booking], int]:
        base = self._visibility_filter(select(Booking), user)

        total = (
            await self.db.execute(select(func.count()).select_from(base.subquery()))
        ).scalar_one()

        stmt = (
            base.order_by(Booking.created_at.desc()).limit(limit).offset(offset)
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        return rows, total

    async def get_by_id(self, booking_id: uuid.UUID) -> Booking | None:
        stmt = select(Booking).where(Booking.id == booking_id)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_visible(self, booking_id: uuid.UUID, user: User) -> Booking | None:
        stmt = self._visibility_filter(
            select(Booking).where(Booking.id == booking_id), user
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    def _visibility_filter(self, stmt, user: User):
        if user.role == UserRole.SUPER_ADMIN:
            return stmt
        if user.role == UserRole.ADMIN:
            return (
                stmt.join(RoomCategory, Booking.room_category_id == RoomCategory.id)
                .join(Sanatorium, RoomCategory.sanatorium_id == Sanatorium.id)
                .where(Sanatorium.admin_user_id == user.id)
            )
        # customer / agent — own bookings only
        return stmt.where(Booking.user_id == user.id)

    # ── cancel ─────────────────────────────────────────────────────────────

    async def cancel(self, booking: Booking, user: User) -> Booking:
        self._assert_can_cancel(booking, user)

        avail_rows = list(
            (
                await self.db.execute(
                    select(RoomAvailability)
                    .where(
                        RoomAvailability.room_category_id == booking.room_category_id,
                        RoomAvailability.date >= booking.check_in,
                        RoomAvailability.date < booking.check_out,
                    )
                    .with_for_update()
                )
            ).scalars()
        )

        for row in avail_rows:
            row.units_available = min(row.units_available + 1, row.units_total)

        booking.status = BookingStatus.CANCELLED
        await notify_booking_cancelled(self.db, booking.id)
        await self.db.commit()
        await self.db.refresh(booking)
        return booking

    def _assert_can_cancel(self, booking: Booking, user: User) -> None:
        if booking.status not in _CANCELLABLE:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Booking cannot be cancelled (status: {booking.status})",
            )
        if user.role == UserRole.SUPER_ADMIN:
            return
        if user.role == UserRole.ADMIN:
            return  # RBAC already checked at router level via get_visible
        if booking.user_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not allowed to cancel this booking",
            )


def get_booking_service(db: AsyncSession = Depends(get_db)) -> BookingService:
    return BookingService(db)
