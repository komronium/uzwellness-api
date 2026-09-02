import uuid
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import and_, case, func, select

from app.models.booking import Booking, BookingStatus, BookingType
from app.models.package import Package
from app.models.payment import Payment, PaymentStatus
from app.models.program import TreatmentProgram
from app.models.room import Room
from app.models.sanatorium import Sanatorium
from app.core.utils import TASHKENT_TZ
from app.models.user import User, UserRole

CENTS = Decimal("0.01")
ZERO = Decimal("0")


def money(value) -> Decimal:
    return Decimal(value or 0).quantize(CENTS)


def assert_finance_role(actor: User) -> None:
    if actor.role not in {UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.AGENT}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Financial reports are only available to property "
                "administrators, platform administrators and B2B agents."
            ),
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
    booking_status: BookingStatus | None = None,
    booking_type: BookingType | None = None,
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
    if booking_status is not None:
        filters.append(Booking.status == booking_status)
    if booking_type is not None:
        filters.append(Booking.booking_type == booking_type)
    return filters


def payment_rollup_subquery():
    """Per-booking payment totals, in the booking's own currency.

    ``payments.amount`` is denominated in the payment's currency, not the
    booking's: Uzum only settles in UZS, so a USD stay paid by card stores a
    six-figure UZS amount. Summing those next to a USD ``final_price`` produced
    totals that were arithmetically meaningless and made a partly paid
    non-UZS booking impossible to spot. Only same-currency payments are added
    up here; the rest are counted, so a booking settled in another currency
    shows as "0 paid, 1 foreign payment" instead of silently inflating a total.
    """

    same_currency = Payment.currency == Booking.currency
    return (
        select(
            Payment.booking_id.label("booking_id"),
            func.count(Payment.id)
            .filter(~same_currency, Payment.status == PaymentStatus.PAID)
            .label("foreign_payment_count"),
            func.coalesce(
                func.sum(Payment.amount).filter(
                    same_currency, Payment.status == PaymentStatus.PAID
                ),
                0,
            ).label("paid_amount"),
            func.coalesce(
                func.sum(Payment.amount).filter(
                    same_currency, Payment.status == PaymentStatus.PENDING
                ),
                0,
            ).label("pending_amount"),
            func.coalesce(
                func.sum(Payment.amount).filter(
                    same_currency, Payment.status == PaymentStatus.REFUND_PENDING
                ),
                0,
            ).label("refund_pending_amount"),
            func.coalesce(
                func.sum(Payment.amount).filter(
                    same_currency, Payment.status == PaymentStatus.REFUNDED
                ),
                0,
            ).label("refunded_amount"),
        )
        .join(Booking, Payment.booking_id == Booking.id)
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


def payment_status_expr(payments):
    """SQL mirror of :func:`payment_status`, evaluated against a payment rollup.

    Returns a CASE expression yielding the exact same string the response shows,
    so filtering by ``payment_status`` can never diverge from the displayed value.
    The branch order must stay identical to :func:`payment_status`.
    """
    paid = func.coalesce(payments.c.paid_amount, 0)
    pending = func.coalesce(payments.c.pending_amount, 0)
    refund_pending = func.coalesce(payments.c.refund_pending_amount, 0)
    refunded = func.coalesce(payments.c.refunded_amount, 0)
    return case(
        (refund_pending > ZERO, "refund_pending"),
        (and_(refunded > ZERO, paid == ZERO, pending == ZERO), "refunded"),
        (and_(Booking.final_price > ZERO, paid >= Booking.final_price), "paid"),
        (paid > ZERO, "partially_paid"),
        (pending > ZERO, "pending"),
        else_="unpaid",
    )


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
    """Midnight in Tashkent, as UTC — the same day boundary the API uses.

    ``created_at`` is stored in UTC, so a UTC midnight put five hours of the
    previous Tashkent day into every report and left the same filter on
    ``/bookings`` and ``/finance/orders`` answering with different rows.
    """

    return datetime.combine(value, time.min, tzinfo=TASHKENT_TZ).astimezone(UTC)


def _next_day(value: date) -> datetime:
    return _start_of_day(value + timedelta(days=1))
