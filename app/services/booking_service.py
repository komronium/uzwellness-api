import uuid
from collections.abc import Sequence

from fastapi import Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.policies import BookingPolicy
from app.core.sanatorium_lookup import sanatorium_name_for_booking
from app.core.utils import today_tashkent
from app.models.availability import RoomAvailability
from app.models.booking import Booking, BookingStatus, BookingType
from app.models.notification import Notification
from app.models.payment import Payment, PaymentStatus
from app.models.user import User, UserRole
from app.schemas.booking import BookingCreate
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
    ) -> tuple[Sequence[Booking], int]:
        filters = booking_visibility_clauses(user)
        if is_b2b is not None:
            filters.append(Booking.is_b2b.is_(is_b2b))
        if agent_id is not None and user.role == UserRole.SUPER_ADMIN:
            filters.append(Booking.user_id == agent_id)

        base = select(Booking)
        for clause in filters:
            base = base.where(clause)
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
