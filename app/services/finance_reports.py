from sqlalchemy import case, func, select
from sqlalchemy.orm import aliased

from app.core.utils import pick_locale
from app.models.booking import Booking, BookingStatus
from app.models.package import Package
from app.models.program import TreatmentProgram
from app.models.room import Room
from app.models.sanatorium import Sanatorium
from app.models.user import User
from app.services.finance_rules import (
    ZERO,
    money,
    payment_rollup_subquery,
    payment_status,
    payment_status_expr,
)


def summary_statement(filters: list, *, payment_status: str | None = None):
    payments = payment_rollup_subquery()
    active = Booking.status != BookingStatus.CANCELLED
    gross = case((active, Booking.final_price), else_=ZERO)
    cancelled_gross = case(
        (Booking.status == BookingStatus.CANCELLED, Booking.final_price),
        else_=ZERO,
    )
    commission = case(
        (active, func.coalesce(Booking.commission_snapshot, 0)),
        else_=ZERO,
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
            func.coalesce(func.sum(cancelled_gross), 0).label("cancelled_gross_amount"),
            func.coalesce(func.sum(payments.c.paid_amount), 0).label("paid_amount"),
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
    stmt = _with_filters(stmt, filters)
    if payment_status is not None:
        stmt = stmt.where(payment_status_expr(payments) == payment_status)
    return stmt


def order_count_statement(filters: list, *, payment_status: str | None = None):
    stmt = select(func.count(Booking.id))
    if payment_status is not None:
        payments = payment_rollup_subquery()
        stmt = stmt.outerjoin(payments, payments.c.booking_id == Booking.id)
        stmt = _with_filters(stmt, filters)
        return stmt.where(payment_status_expr(payments) == payment_status)
    return _with_filters(stmt, filters)


def orders_statement(
    filters: list, *, limit: int, offset: int, payment_status: str | None = None
):
    payments = payment_rollup_subquery()
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
        .outerjoin(package_sanatorium, Package.sanatorium_id == package_sanatorium.id)
        .order_by(Booking.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    stmt = _with_filters(stmt, filters)
    if payment_status is not None:
        stmt = stmt.where(payment_status_expr(payments) == payment_status)
    return stmt


def summary_item(row, *, can_see_internal: bool) -> dict:
    return {
        "currency": row.currency,
        "booking_count": int(row.booking_count),
        "cancelled_bookings": int(row.cancelled_bookings),
        "b2b_bookings": int(row.b2b),
        "b2c_bookings": int(row.b2c),
        "gross_amount": money(row.gross_amount),
        "cancelled_gross_amount": money(row.cancelled_gross_amount),
        "paid_amount": money(row.paid_amount),
        "pending_payment_amount": money(row.pending_payment_amount),
        "refund_pending_amount": money(row.refund_pending_amount),
        "refunded_amount": money(row.refunded_amount),
        "platform_commission_amount": (
            money(row.commission_amount) if can_see_internal else None
        ),
        "sanatorium_net_amount": money(row.net_amount) if can_see_internal else None,
    }


def order_item(row, *, can_see_internal: bool) -> dict:
    booking = row[0]
    amounts = _order_payment_amounts(row)
    commission_amount = money(booking.commission_snapshot)
    active = booking.status != BookingStatus.CANCELLED
    net_amount = money(booking.final_price - commission_amount) if active else ZERO

    return {
        "booking_id": booking.id,
        "booking_code": booking.code,
        "booking_type": booking.booking_type,
        "booking_status": booking.status,
        "payment_status": payment_status(
            booking,
            paid_amount=amounts["paid_amount"],
            pending_amount=amounts["pending_amount"],
            refund_pending_amount=amounts["refund_pending_amount"],
            refunded_amount=amounts["refunded_amount"],
        ),
        "sanatorium_id": row.sanatorium_id,
        "sanatorium_name": _localized_name(row.sanatorium_name),
        "agent_id": booking.user_id if booking.is_b2b else None,
        "agent_email": row.agent_email if booking.is_b2b else None,
        "agent_name": row.agent_name if booking.is_b2b else None,
        "is_b2b": booking.is_b2b,
        "gross_amount": money(booking.final_price) if active else ZERO,
        "paid_amount": amounts["paid_amount"],
        "pending_payment_amount": amounts["pending_amount"],
        "refund_pending_amount": amounts["refund_pending_amount"],
        "refunded_amount": amounts["refunded_amount"],
        "commission_percent": (
            money(booking.commission_percent_snapshot) if can_see_internal else None
        ),
        "platform_commission_amount": (
            (commission_amount if active else ZERO) if can_see_internal else None
        ),
        "sanatorium_net_amount": net_amount if can_see_internal else None,
        "agent_discount_percent": booking.agent_discount_percent_snapshot,
        "currency": booking.currency,
        "check_in": booking.check_in,
        "created_at": booking.created_at,
    }


def _order_payment_amounts(row) -> dict:
    return {
        "paid_amount": money(row.paid_amount),
        "pending_amount": money(row.pending_amount),
        "refund_pending_amount": money(row.refund_pending_amount),
        "refunded_amount": money(row.refunded_amount),
    }


def _localized_name(value) -> str | None:
    return pick_locale(value) if value else None


def _with_filters(stmt, filters: list):
    for clause in filters:
        stmt = stmt.where(clause)
    return stmt
