import uuid
from collections.abc import Sequence

from fastapi import Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.notifier import BookingNotifier, get_booking_notifier
from app.core.policies import BookingPolicy
from app.core.sanatorium_lookup import sanatorium_name_for_booking
from app.core.utils import today_tashkent
from app.models.availability import RoomAvailability
from app.models.booking import Booking, BookingStatus, BookingType
from app.models.notification import Notification
from app.models.package import Package
from app.models.payment import Payment, PaymentStatus
from app.models.program import TreatmentProgram
from app.models.room import Room
from app.models.sanatorium import Sanatorium
from app.models.user import User, UserRole
from app.schemas.booking import BookingCreate
from app.services.booking_flows import (
    BookingFlow,
    PackageBookingFlow,
    RoomBookingFlow,
    SessionBookingFlow,
)
from app.services.booking_pricing_policy import BookingPricingPolicy
from app.services.email_service import BookingEmailContext

_LOAD_OPTIONS = (
    selectinload(Booking.extra_beds),
    selectinload(Booking.user),
    selectinload(Booking.payments),
)


class BookingService:
    """Routes booking requests to a matching flow; handles cancel/list/visibility."""

    def __init__(
        self,
        db: AsyncSession,
        notifier: BookingNotifier,
        flows: Sequence[BookingFlow],
    ) -> None:
        self.db = db
        self.notifier = notifier
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
        filters = self._visibility_clauses(user)
        if is_b2b is not None:
            filters.append(Booking.is_b2b.is_(is_b2b))
        if agent_id is not None and user.role == UserRole.SUPER_ADMIN:
            filters.append(Booking.user_id == agent_id)

        base = select(Booking)
        for clause in filters:
            base = base.where(clause)
        total = await self.db.scalar(
            select(func.count()).select_from(base.subquery())
        )
        stmt = (
            base.options(*_LOAD_OPTIONS)
            .order_by(Booking.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = (await self.db.scalars(stmt)).all()
        return rows, total or 0

    async def get_visible(self, booking_id: uuid.UUID, user: User) -> Booking | None:
        stmt = (
            select(Booking)
            .options(*_LOAD_OPTIONS)
            .where(Booking.id == booking_id)
        )
        for clause in self._visibility_clauses(user):
            stmt = stmt.where(clause)
        return await self.db.scalar(stmt)

    async def cancel(self, booking: Booking, user: User) -> Booking:
        await self._assert_can_cancel(booking, user)

        if (
            booking.booking_type in (BookingType.ROOM, BookingType.PACKAGE)
            and booking.room_id is not None
        ):
            avail_rows = (
                await self.db.scalars(
                    select(RoomAvailability)
                    .where(
                        RoomAvailability.room_id == booking.room_id,
                        RoomAvailability.date >= booking.check_in,
                        RoomAvailability.date < booking.check_out,
                    )
                    .with_for_update()
                )
            ).all()
            for row in avail_rows:
                row.units_booked = max(row.units_booked - booking.rooms_count, 0)

        booking.status = BookingStatus.CANCELLED
        # Flip payments into refund-pending / cancelled. Actual refund
        # processing is gateway-specific and out of scope here — this just
        # gives finance a queryable list of money to return.
        await self._mark_payments_for_refund(booking.id)
        self.db.add(
            Notification(
                booking_id=booking.id, type="booking_cancelled", channel="email"
            )
        )
        await self.db.commit()

        sanatorium_name = await sanatorium_name_for_booking(self.db, booking)
        if sanatorium_name is not None:
            await self._notify_cancelled(booking, user, sanatorium_name)
        return await self._load(booking.id)  # type: ignore[return-value]

    def _visibility_clauses(self, user: User) -> list:
        if user.role == UserRole.SUPER_ADMIN:
            return []
        if user.role == UserRole.ADMIN:
            room_sub = (
                select(Room.id)
                .join(Sanatorium, Room.sanatorium_id == Sanatorium.id)
                .where(Sanatorium.admin_user_id == user.id)
                .scalar_subquery()
            )
            program_sub = (
                select(TreatmentProgram.id)
                .join(Sanatorium, TreatmentProgram.sanatorium_id == Sanatorium.id)
                .where(Sanatorium.admin_user_id == user.id)
                .scalar_subquery()
            )
            package_sub = (
                select(Package.id)
                .join(Sanatorium, Package.sanatorium_id == Sanatorium.id)
                .where(Sanatorium.admin_user_id == user.id)
                .scalar_subquery()
            )
            return [
                Booking.room_id.in_(room_sub)
                | Booking.program_id.in_(program_sub)
                | Booking.package_id.in_(package_sub)
            ]
        return [Booking.user_id == user.id]

    async def _assert_can_cancel(self, booking: Booking, user: User) -> None:
        admin_owns = False
        if user.role == UserRole.ADMIN:
            admin_owns = await self._admin_owns_booking_sanatorium(booking, user)
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

    async def _admin_owns_booking_sanatorium(
        self, booking: Booking, user: User
    ) -> bool:
        """Does the admin actor own the sanatorium this booking belongs to?

        Resolves the booking's sanatorium via whichever link is set
        (room/program/package). Returns False if no link survives — a
        cancelled-and-detached booking can't be re-cancelled by an admin
        whose ownership can't be traced.
        """
        sanatorium_id: uuid.UUID | None = None
        if booking.room_id is not None:
            sanatorium_id = await self.db.scalar(
                select(Room.sanatorium_id).where(Room.id == booking.room_id)
            )
        elif booking.program_id is not None:
            sanatorium_id = await self.db.scalar(
                select(TreatmentProgram.sanatorium_id).where(
                    TreatmentProgram.id == booking.program_id
                )
            )
        elif booking.package_id is not None:
            sanatorium_id = await self.db.scalar(
                select(Package.sanatorium_id).where(
                    Package.id == booking.package_id
                )
            )

        if sanatorium_id is None:
            return False
        admin_id = await self.db.scalar(
            select(Sanatorium.admin_user_id).where(Sanatorium.id == sanatorium_id)
        )
        return admin_id == user.id

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

    async def _notify_cancelled(
        self, booking: Booking, user: User, sanatorium_name: str
    ) -> None:
        if not user.email:
            return
        ctx = BookingEmailContext(
            booking_code=booking.code,
            sanatorium_name=sanatorium_name,
            check_in=booking.check_in,
            check_out=booking.check_out,
            guest_name=user.full_name or user.email,
            total_price=booking.final_price,
            currency=booking.currency,
        )
        self.notifier.booking_cancelled(to=user.email, ctx=ctx)


def get_booking_service(
    db: AsyncSession = Depends(get_db),
    notifier: BookingNotifier = Depends(get_booking_notifier),
) -> BookingService:
    pricing = BookingPricingPolicy(db)
    flows: list[BookingFlow] = [
        SessionBookingFlow(db, pricing, notifier),
        PackageBookingFlow(db, pricing, notifier),
        RoomBookingFlow(db, pricing, notifier),
    ]
    return BookingService(db, notifier, flows)
