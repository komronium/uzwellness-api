import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime, time, timedelta

from fastapi import Depends, HTTPException, status
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.policies import BookingPolicy
from app.core.sanatorium_lookup import sanatorium_name_for_booking
from app.core.utils import TASHKENT_TZ, today_tashkent
from app.models.availability import RoomAvailability
from app.models.booking import Booking, BookingStatus, BookingType
from app.models.cancellation import CancellationRequest, CancellationStatus
from app.models.notification import Notification
from app.models.payment import Payment, PaymentStatus
from app.models.user import User, UserRole
from app.schemas.booking import (
    BookingCreate,
    BookingDateFilter,
)
from app.services.booking_flows import (
    BookingFlow,
    PackageBookingFlow,
    RoomBookingFlow,
    SessionBookingFlow,
)
from app.services.booking_pricing_policy import BookingPricingPolicy
from app.services.booking_visibility import (
    admin_owns_booking_sanatorium,
    booking_visibility_clauses,
)
from app.services.email_service import BookingEmailContext, send_booking_cancelled

_LOAD_OPTIONS = (
    selectinload(Booking.extra_beds),
    selectinload(Booking.user),
    selectinload(Booking.payments),
)


class BookingService:
    def __init__(
        self,
        db: AsyncSession,
        flows: Sequence[BookingFlow],
    ) -> None:
        self.db = db
        self.flows = flows

    async def create(self, payload: BookingCreate, user: User) -> Booking:
        if payload.check_in < today_tashkent():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="check_in must be today or in the future",
            )
        for flow in self.flows:
            if flow.matches(payload):
                return await flow.create(payload, user)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="One of room_id, program_id, or package_id is required",
        )

    async def list_for_user(
        self,
        user: User,
        *,
        limit: int,
        offset: int,
        is_b2b: bool | None = None,
        agent_id: uuid.UUID | None = None,
        q: str | None = None,
        status_filter: BookingStatus | None = None,
        is_processed: bool | None = None,
        cancellation_status: CancellationStatus | None = None,
        date_filter: BookingDateFilter = BookingDateFilter.BOOKING_DATE,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> tuple[Sequence[Booking], int]:
        filters = booking_visibility_clauses(user)
        if is_b2b is not None:
            filters.append(Booking.is_b2b.is_(is_b2b))
        if agent_id is not None and user.role == UserRole.SUPER_ADMIN:
            filters.append(Booking.user_id == agent_id)
        if status_filter is not None:
            filters.append(Booking.status == status_filter)
        if is_processed is not None:
            filters.append(Booking.is_processed.is_(is_processed))
        if cancellation_status is not None:
            filters.append(
                select(CancellationRequest.id)
                .where(
                    CancellationRequest.booking_id == Booking.id,
                    CancellationRequest.status == cancellation_status,
                )
                .exists()
            )

        base = select(Booking).outerjoin(User, Booking.user_id == User.id)
        for clause in filters:
            base = base.where(clause)
        if q:
            term = f"%{q.strip()}%"
            base = base.where(
                or_(
                    Booking.code.ilike(term),
                    Booking.reservation_number.ilike(term),
                    User.full_name.ilike(term),
                    User.email.ilike(term),
                )
            )
        base = self._apply_date_filters(
            base, date_filter=date_filter, date_from=date_from, date_to=date_to
        )
        total = await self.db.scalar(select(func.count()).select_from(base.subquery()))
        stmt = (
            base.options(*_LOAD_OPTIONS)
            .order_by(Booking.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = (await self.db.scalars(stmt)).all()
        return rows, total or 0

    async def get_visible(self, booking_id: uuid.UUID, user: User) -> Booking | None:
        stmt = select(Booking).options(*_LOAD_OPTIONS).where(Booking.id == booking_id)
        for clause in booking_visibility_clauses(user):
            stmt = stmt.where(clause)
        return await self.db.scalar(stmt)

    async def get_visible_by_reference(
        self, booking_ref: str, user: User
    ) -> Booking | None:
        try:
            booking_id = uuid.UUID(booking_ref)
        except ValueError:
            return await self.get_visible_by_reservation_number(booking_ref, user)
        return await self.get_visible(booking_id, user)

    async def get_visible_by_reservation_number(
        self, reservation_number: str, user: User
    ) -> Booking | None:
        digits = "".join(ch for ch in reservation_number if ch.isdigit())
        if not digits:
            return None
        stmt = (
            select(Booking)
            .options(*_LOAD_OPTIONS)
            .where(Booking.reservation_number == digits)
        )
        for clause in booking_visibility_clauses(user):
            stmt = stmt.where(clause)
        return await self.db.scalar(stmt)

    async def mark_processed(self, booking: Booking, user: User) -> Booking:
        if user.role not in {UserRole.ADMIN, UserRole.SUPER_ADMIN}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only sanatorium staff can process reservations",
            )
        locked = await self.db.scalar(
            select(Booking).where(Booking.id == booking.id).with_for_update()
        )
        if locked is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found"
            )
        locked.is_processed = True
        locked.processed_at = datetime.now(UTC)
        locked.processed_by_id = user.id
        await self.db.commit()
        return await self._load_required(locked.id)

    async def cancel(self, booking: Booking, user: User) -> Booking:
        locked = await self.db.scalar(
            select(Booking).where(Booking.id == booking.id).with_for_update()
        )
        if locked is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found"
            )
        await self._assert_can_cancel(locked, user)

        if (
            locked.booking_type in (BookingType.ROOM, BookingType.PACKAGE)
            and locked.room_id is not None
        ):
            avail_rows = (
                await self.db.scalars(
                    select(RoomAvailability)
                    .where(
                        RoomAvailability.room_id == locked.room_id,
                        RoomAvailability.date >= locked.check_in,
                        RoomAvailability.date < locked.check_out,
                    )
                    .with_for_update()
                )
            ).all()
            for row in avail_rows:
                row.units_booked = max(row.units_booked - locked.rooms_count, 0)

        locked.status = BookingStatus.CANCELLED
        await self._mark_payments_for_refund(locked.id)
        self.db.add(
            Notification(
                booking_id=locked.id, type="booking_cancelled", channel="email"
            )
        )
        await self.db.commit()

        sanatorium_name = await sanatorium_name_for_booking(self.db, locked)
        if sanatorium_name is not None:
            self._notify_cancelled(locked, user, sanatorium_name)
        return await self._load_required(locked.id)

    async def _assert_can_cancel(self, booking: Booking, user: User) -> None:
        admin_owns = False
        if user.role == UserRole.ADMIN:
            admin_owns = await admin_owns_booking_sanatorium(self.db, booking, user.id)
        reason = BookingPolicy.cancel_block_reason(
            booking, user, admin_owns_target=admin_owns
        )
        if reason is None:
            return
        status_code = (
            status.HTTP_409_CONFLICT
            if booking.status not in {BookingStatus.PENDING, BookingStatus.CONFIRMED}
            else status.HTTP_403_FORBIDDEN
        )
        raise HTTPException(status_code=status_code, detail=reason)

    async def _mark_payments_for_refund(self, booking_id: uuid.UUID) -> None:
        payments = (
            await self.db.scalars(
                select(Payment).where(Payment.booking_id == booking_id)
            )
        ).all()
        for p in payments:
            if p.status == PaymentStatus.PAID:
                p.status = PaymentStatus.REFUND_PENDING
            elif p.status == PaymentStatus.PENDING:
                p.status = PaymentStatus.CANCELLED

    async def _load(self, booking_id: uuid.UUID) -> Booking | None:
        return await self.db.scalar(
            select(Booking).options(*_LOAD_OPTIONS).where(Booking.id == booking_id)
        )

    async def _load_required(self, booking_id: uuid.UUID) -> Booking:
        booking = await self._load(booking_id)
        if booking is None:
            raise RuntimeError(f"Booking {booking_id} not found after write")
        return booking

    @staticmethod
    def _apply_date_filters(
        stmt,
        *,
        date_filter: BookingDateFilter,
        date_from: date | None,
        date_to: date | None,
    ):
        if date_from is None and date_to is None:
            return stmt
        if date_filter == BookingDateFilter.BOOKING_DATE:
            if date_from is not None:
                stmt = stmt.where(Booking.created_at >= _day_bounds(date_from)[0])
            if date_to is not None:
                stmt = stmt.where(Booking.created_at < _day_bounds(date_to)[1])
            return stmt
        field = (
            Booking.check_in
            if date_filter == BookingDateFilter.CHECK_IN
            else Booking.check_out
        )
        if date_from is not None:
            stmt = stmt.where(field >= date_from)
        if date_to is not None:
            stmt = stmt.where(field <= date_to)
        return stmt

    @staticmethod
    def _notify_cancelled(booking: Booking, user: User, sanatorium_name: str) -> None:
        if not user.email:
            return
        send_booking_cancelled(
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


def get_booking_service(
    db: AsyncSession = Depends(get_db),
) -> BookingService:
    pricing = BookingPricingPolicy(db)
    flows: list[BookingFlow] = [
        SessionBookingFlow(db, pricing),
        PackageBookingFlow(db, pricing),
        RoomBookingFlow(db, pricing),
    ]
    return BookingService(db, flows)


async def complete_past_bookings(db: AsyncSession) -> int:
    """Move confirmed stays whose check_out has passed to COMPLETED.

    Run daily (scripts/complete_bookings.py); pending bookings are left
    untouched — an unpaid past booking is not a completed stay.
    """
    result = await db.execute(
        update(Booking)
        .where(
            Booking.status == BookingStatus.CONFIRMED,
            Booking.check_out < today_tashkent(),
        )
        .values(status=BookingStatus.COMPLETED)
    )
    await db.commit()
    return result.rowcount or 0


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=TASHKENT_TZ).astimezone(UTC)
    return start, start + timedelta(days=1)
