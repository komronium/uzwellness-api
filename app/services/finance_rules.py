import uuid
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select

from app.models.booking import Booking
from app.models.package import Package
from app.models.payment import Payment, PaymentStatus
from app.models.program import TreatmentProgram
from app.models.room import Room
from app.models.sanatorium import Sanatorium
from app.models.user import User, UserRole

CENTS = Decimal("0.01")
ZERO = Decimal("0")


def money(value) -> Decimal:
    return Decimal(value or 0).quantize(CENTS)


def assert_finance_role(actor: User) -> None:
    if actor.role not in {UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.AGENT}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Finance access required",
        )


def can_see_internal_finance(actor: User) -> bool:
    return actor.role in {UserRole.SUPER_ADMIN, UserRole.ADMIN}


def finance_filters(
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
        filters.append(booking_belongs_to_admin(actor.id))
    elif actor.role == UserRole.AGENT:
        filters.append(Booking.user_id == actor.id)
        filters.append(Booking.is_b2b.is_(True))
    elif agent_id is not None:
        filters.append(Booking.user_id == agent_id)

    if sanatorium_id is not None:
        filters.append(booking_belongs_to_sanatorium(sanatorium_id))
    if is_b2b is not None:
        filters.append(Booking.is_b2b.is_(is_b2b))
    if date_from is not None:
        filters.append(Booking.created_at >= _start_of_day(date_from))
    if date_to is not None:
        filters.append(Booking.created_at < _next_day(date_to))
    return filters


def payment_rollup_subquery():
    return (
        select(
            Payment.booking_id.label("booking_id"),
            func.coalesce(
                func.sum(Payment.amount).filter(Payment.status == PaymentStatus.PAID),
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


def payment_status(
    booking: Booking,
    *,
    paid_amount: Decimal,
    pending_amount: Decimal,
    refund_pending_amount: Decimal,
    refunded_amount: Decimal,
) -> str:
    if refund_pending_amount > ZERO:
        return "refund_pending"
    if refunded_amount > ZERO and paid_amount == ZERO and pending_amount == ZERO:
        return "refunded"
    if booking.final_price > ZERO and paid_amount >= booking.final_price:
        return "paid"
    if paid_amount > ZERO:
        return "partially_paid"
    if pending_amount > ZERO:
        return "pending"
    return "unpaid"


def booking_belongs_to_sanatorium(sanatorium_id: uuid.UUID):
    room_subquery = (
        select(Room.id).where(Room.sanatorium_id == sanatorium_id).scalar_subquery()
    )
    program_subquery = (
        select(TreatmentProgram.id)
        .where(TreatmentProgram.sanatorium_id == sanatorium_id)
        .scalar_subquery()
    )
    package_subquery = (
        select(Package.id)
        .where(Package.sanatorium_id == sanatorium_id)
        .scalar_subquery()
    )
    return (
        Booking.room_id.in_(room_subquery)
        | Booking.program_id.in_(program_subquery)
        | Booking.package_id.in_(package_subquery)
    )


def booking_belongs_to_admin(admin_id: uuid.UUID):
    room_subquery = (
        select(Room.id)
        .join(Sanatorium, Room.sanatorium_id == Sanatorium.id)
        .where(Sanatorium.admin_user_id == admin_id)
        .scalar_subquery()
    )
    program_subquery = (
        select(TreatmentProgram.id)
        .join(Sanatorium, TreatmentProgram.sanatorium_id == Sanatorium.id)
        .where(Sanatorium.admin_user_id == admin_id)
        .scalar_subquery()
    )
    package_subquery = (
        select(Package.id)
        .join(Sanatorium, Package.sanatorium_id == Sanatorium.id)
        .where(Sanatorium.admin_user_id == admin_id)
        .scalar_subquery()
    )
    return (
        Booking.room_id.in_(room_subquery)
        | Booking.program_id.in_(program_subquery)
        | Booking.package_id.in_(package_subquery)
    )


def _start_of_day(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=UTC)


def _next_day(value: date) -> datetime:
    return datetime.combine(value + timedelta(days=1), time.min, tzinfo=UTC)
