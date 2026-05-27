import uuid
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from fastapi import Depends, HTTPException, status
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.database import get_db
from app.core.utils import pick_locale
from app.models.booking import Booking, BookingStatus
from app.models.package import Package
from app.models.payment import Payment, PaymentStatus
from app.models.program import TreatmentProgram
from app.models.room import Room
from app.models.sanatorium import Sanatorium
from app.models.user import User, UserRole

_CENTS = Decimal("0.01")
_ZERO = Decimal("0")


def _money(value) -> Decimal:
    return Decimal(value or 0).quantize(_CENTS)


def _start_of_day(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=UTC)


def _next_day(value: date) -> datetime:
    return datetime.combine(value + timedelta(days=1), time.min, tzinfo=UTC)


class FinanceService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def summary(
        self,
        actor: User,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        sanatorium_id: uuid.UUID | None = None,
        agent_id: uuid.UUID | None = None,
        is_b2b: bool | None = None,
    ) -> dict:
        self._assert_finance_role(actor)
        payments = self._payment_rollup_subquery()
        active = Booking.status != BookingStatus.CANCELLED
        gross = case((active, Booking.final_price), else_=_ZERO)
        cancelled_gross = case(
            (Booking.status == BookingStatus.CANCELLED, Booking.final_price),
            else_=_ZERO,
        )
        commission = case(
            (active, func.coalesce(Booking.commission_snapshot, 0)),
            else_=_ZERO,
        )

        stmt = (
            select(
                Booking.currency.label("currency"),
                func.count(Booking.id).label("booking_count"),
                func.count(Booking.id)
                .filter(Booking.status == BookingStatus.CANCELLED)
                .label("cancelled_bookings"),
                func.count(Booking.id).filter(Booking.is_b2b.is_(True)).label("b2b"),
                func.count(Booking.id).filter(Booking.is_b2b.is_(False)).label("b2c"),
                func.coalesce(func.sum(gross), 0).label("gross_amount"),
                func.coalesce(func.sum(cancelled_gross), 0).label(
                    "cancelled_gross_amount"
                ),
                func.coalesce(func.sum(payments.c.paid_amount), 0).label(
                    "paid_amount"
                ),
                func.coalesce(func.sum(payments.c.pending_amount), 0).label(
                    "pending_payment_amount"
                ),
                func.coalesce(func.sum(payments.c.refund_pending_amount), 0).label(
                    "refund_pending_amount"
                ),
                func.coalesce(func.sum(payments.c.refunded_amount), 0).label(
                    "refunded_amount"
                ),
                func.coalesce(func.sum(commission), 0).label("commission_amount"),
                func.coalesce(func.sum(gross - commission), 0).label("net_amount"),
            )
            .outerjoin(payments, payments.c.booking_id == Booking.id)
            .group_by(Booking.currency)
            .order_by(Booking.currency)
        )
        for clause in self._filters(
            actor,
            date_from=date_from,
            date_to=date_to,
            sanatorium_id=sanatorium_id,
            agent_id=agent_id,
            is_b2b=is_b2b,
        ):
            stmt = stmt.where(clause)

        can_see_internal = self._can_see_internal_finance(actor)
        rows = (await self.db.execute(stmt)).all()
        return {
            "items": [
                {
                    "currency": row.currency,
                    "booking_count": int(row.booking_count),
                    "cancelled_bookings": int(row.cancelled_bookings),
                    "b2b_bookings": int(row.b2b),
                    "b2c_bookings": int(row.b2c),
                    "gross_amount": _money(row.gross_amount),
                    "cancelled_gross_amount": _money(row.cancelled_gross_amount),
                    "paid_amount": _money(row.paid_amount),
                    "pending_payment_amount": _money(row.pending_payment_amount),
                    "refund_pending_amount": _money(row.refund_pending_amount),
                    "refunded_amount": _money(row.refunded_amount),
                    "platform_commission_amount": (
                        _money(row.commission_amount) if can_see_internal else None
                    ),
                    "sanatorium_net_amount": (
                        _money(row.net_amount) if can_see_internal else None
                    ),
                }
                for row in rows
            ]
        }

    async def orders(
        self,
        actor: User,
        *,
        limit: int,
        offset: int,
        date_from: date | None = None,
        date_to: date | None = None,
        sanatorium_id: uuid.UUID | None = None,
        agent_id: uuid.UUID | None = None,
        is_b2b: bool | None = None,
    ) -> tuple[list[dict], int]:
        self._assert_finance_role(actor)
        filters = self._filters(
            actor,
            date_from=date_from,
            date_to=date_to,
            sanatorium_id=sanatorium_id,
            agent_id=agent_id,
            is_b2b=is_b2b,
        )
        total_stmt = select(func.count(Booking.id))
        for clause in filters:
            total_stmt = total_stmt.where(clause)
        total = await self.db.scalar(total_stmt)

        payments = self._payment_rollup_subquery()
        room_sanatorium = aliased(Sanatorium)
        program_sanatorium = aliased(Sanatorium)
        package_sanatorium = aliased(Sanatorium)

        stmt = (
            select(
                Booking,
                func.coalesce(
                    room_sanatorium.id,
                    program_sanatorium.id,
                    package_sanatorium.id,
                ).label("sanatorium_id"),
                func.coalesce(
                    room_sanatorium.name,
                    program_sanatorium.name,
                    package_sanatorium.name,
                ).label("sanatorium_name"),
                User.email.label("agent_email"),
                User.full_name.label("agent_name"),
                payments.c.paid_amount,
                payments.c.pending_amount,
                payments.c.refund_pending_amount,
                payments.c.refunded_amount,
            )
            .outerjoin(payments, payments.c.booking_id == Booking.id)
            .outerjoin(User, Booking.user_id == User.id)
            .outerjoin(Room, Booking.room_id == Room.id)
            .outerjoin(room_sanatorium, Room.sanatorium_id == room_sanatorium.id)
            .outerjoin(TreatmentProgram, Booking.program_id == TreatmentProgram.id)
            .outerjoin(
                program_sanatorium,
                TreatmentProgram.sanatorium_id == program_sanatorium.id,
            )
            .outerjoin(Package, Booking.package_id == Package.id)
            .outerjoin(
                package_sanatorium,
                Package.sanatorium_id == package_sanatorium.id,
            )
            .order_by(Booking.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        for clause in filters:
            stmt = stmt.where(clause)

        can_see_internal = self._can_see_internal_finance(actor)
        rows = (await self.db.execute(stmt)).all()
        items: list[dict] = []
        for (
            booking,
            resolved_sanatorium_id,
            resolved_sanatorium_name,
            agent_email,
            agent_name,
            paid_value,
            pending_value,
            refund_pending_value,
            refunded_value,
        ) in rows:
            paid_amount = _money(paid_value)
            pending_amount = _money(pending_value)
            refund_pending_amount = _money(refund_pending_value)
            refunded_amount = _money(refunded_value)
            commission_amount = _money(booking.commission_snapshot)
            active = booking.status != BookingStatus.CANCELLED
            net_amount = (
                _money(booking.final_price - commission_amount) if active else _ZERO
            )
            items.append(
                {
                    "booking_id": booking.id,
                    "booking_code": booking.code,
                    "booking_type": booking.booking_type,
                    "booking_status": booking.status,
                    "payment_status": self._payment_status(
                        booking,
                        paid_amount=paid_amount,
                        pending_amount=pending_amount,
                        refund_pending_amount=refund_pending_amount,
                        refunded_amount=refunded_amount,
                    ),
                    "sanatorium_id": resolved_sanatorium_id,
                    "sanatorium_name": (
                        pick_locale(resolved_sanatorium_name)
                        if resolved_sanatorium_name
                        else None
                    ),
                    "agent_id": booking.user_id if booking.is_b2b else None,
                    "agent_email": agent_email if booking.is_b2b else None,
                    "agent_name": agent_name if booking.is_b2b else None,
                    "is_b2b": booking.is_b2b,
                    "gross_amount": (
                        _money(booking.final_price) if active else _ZERO
                    ),
                    "paid_amount": paid_amount,
                    "pending_payment_amount": pending_amount,
                    "refund_pending_amount": refund_pending_amount,
                    "refunded_amount": refunded_amount,
                    "commission_percent": (
                        _money(booking.commission_percent_snapshot)
                        if can_see_internal
                        else None
                    ),
                    "platform_commission_amount": (
                        (commission_amount if active else _ZERO)
                        if can_see_internal
                        else None
                    ),
                    "sanatorium_net_amount": (
                        net_amount if can_see_internal else None
                    ),
                    "agent_discount_percent": booking.agent_discount_percent_snapshot,
                    "currency": booking.currency,
                    "check_in": booking.check_in,
                    "created_at": booking.created_at,
                }
            )
        return items, int(total or 0)

    @staticmethod
    def _assert_finance_role(actor: User) -> None:
        if actor.role not in {UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.AGENT}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Finance access required",
            )

    @staticmethod
    def _can_see_internal_finance(actor: User) -> bool:
        return actor.role in {UserRole.SUPER_ADMIN, UserRole.ADMIN}

    def _filters(
        self,
        actor: User,
        *,
        date_from: date | None,
        date_to: date | None,
        sanatorium_id: uuid.UUID | None,
        agent_id: uuid.UUID | None,
        is_b2b: bool | None,
    ) -> list:
        filters: list = []
        if actor.role == UserRole.ADMIN:
            filters.append(self._booking_belongs_to_admin(actor.id))
        elif actor.role == UserRole.AGENT:
            filters.append(Booking.user_id == actor.id)
            filters.append(Booking.is_b2b.is_(True))
        elif agent_id is not None:
            filters.append(Booking.user_id == agent_id)

        if sanatorium_id is not None:
            filters.append(self._booking_belongs_to_sanatorium(sanatorium_id))
        if is_b2b is not None:
            filters.append(Booking.is_b2b.is_(is_b2b))
        if date_from is not None:
            filters.append(Booking.created_at >= _start_of_day(date_from))
        if date_to is not None:
            filters.append(Booking.created_at < _next_day(date_to))
        return filters

    @staticmethod
    def _payment_rollup_subquery():
        return (
            select(
                Payment.booking_id.label("booking_id"),
                func.coalesce(
                    func.sum(Payment.amount).filter(
                        Payment.status == PaymentStatus.PAID
                    ),
                    0,
                ).label("paid_amount"),
                func.coalesce(
                    func.sum(Payment.amount).filter(
                        Payment.status == PaymentStatus.PENDING
                    ),
                    0,
                ).label("pending_amount"),
                func.coalesce(
                    func.sum(Payment.amount).filter(
                        Payment.status == PaymentStatus.REFUND_PENDING
                    ),
                    0,
                ).label("refund_pending_amount"),
                func.coalesce(
                    func.sum(Payment.amount).filter(
                        Payment.status == PaymentStatus.REFUNDED
                    ),
                    0,
                ).label("refunded_amount"),
            )
            .group_by(Payment.booking_id)
            .subquery()
        )

    @staticmethod
    def _payment_status(
        booking: Booking,
        *,
        paid_amount: Decimal,
        pending_amount: Decimal,
        refund_pending_amount: Decimal,
        refunded_amount: Decimal,
    ) -> str:
        if refund_pending_amount > _ZERO:
            return "refund_pending"
        if refunded_amount > _ZERO and paid_amount == _ZERO and pending_amount == _ZERO:
            return "refunded"
        if booking.final_price > _ZERO and paid_amount >= booking.final_price:
            return "paid"
        if paid_amount > _ZERO:
            return "partially_paid"
        if pending_amount > _ZERO:
            return "pending"
        return "unpaid"

    @staticmethod
    def _booking_belongs_to_sanatorium(sanatorium_id: uuid.UUID):
        room_sub = (
            select(Room.id).where(Room.sanatorium_id == sanatorium_id).scalar_subquery()
        )
        program_sub = (
            select(TreatmentProgram.id)
            .where(TreatmentProgram.sanatorium_id == sanatorium_id)
            .scalar_subquery()
        )
        package_sub = (
            select(Package.id)
            .where(Package.sanatorium_id == sanatorium_id)
            .scalar_subquery()
        )
        return (
            Booking.room_id.in_(room_sub)
            | Booking.program_id.in_(program_sub)
            | Booking.package_id.in_(package_sub)
        )

    @staticmethod
    def _booking_belongs_to_admin(admin_id: uuid.UUID):
        room_sub = (
            select(Room.id)
            .join(Sanatorium, Room.sanatorium_id == Sanatorium.id)
            .where(Sanatorium.admin_user_id == admin_id)
            .scalar_subquery()
        )
        program_sub = (
            select(TreatmentProgram.id)
            .join(Sanatorium, TreatmentProgram.sanatorium_id == Sanatorium.id)
            .where(Sanatorium.admin_user_id == admin_id)
            .scalar_subquery()
        )
        package_sub = (
            select(Package.id)
            .join(Sanatorium, Package.sanatorium_id == Sanatorium.id)
            .where(Sanatorium.admin_user_id == admin_id)
            .scalar_subquery()
        )
        return (
            Booking.room_id.in_(room_sub)
            | Booking.program_id.in_(program_sub)
            | Booking.package_id.in_(package_sub)
        )


def get_finance_service(db: AsyncSession = Depends(get_db)) -> FinanceService:
    return FinanceService(db)
