"""What a cancelled booking is owed back under its own cancellation terms."""

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking, BookingStatus, BookingType
from app.models.payment import Payment, PaymentMethod, PaymentStatus
from app.services.booking_service import BookingService, get_booking_service
from app.services.cancellation_policy import refund_for
from tests.factories import make_room, make_sanatorium, make_user


class _Terms:
    """The four fields ``refund_for`` reads, without touching the database."""

    def __init__(
        self,
        *,
        refundable=None,
        free_cancellation_days=None,
        penalty_percent=None,
        penalty_amount=None,
        final_price="1000.00",
        check_in=None,
    ) -> None:
        self.refundable = refundable
        self.free_cancellation_days = free_cancellation_days
        self.cancellation_penalty_percent = (
            Decimal(penalty_percent) if penalty_percent is not None else None
        )
        self.cancellation_penalty_amount = (
            Decimal(penalty_amount) if penalty_amount is not None else None
        )
        self.final_price = Decimal(final_price)
        self.check_in = check_in or date(2026, 6, 20)


_TODAY = date(2026, 6, 1)


def test_a_booking_without_a_rate_plan_is_refunded_in_full():
    """Most bookings carry no terms at all; they must not gain a fee."""

    result = refund_for(_Terms(), Decimal("1000.00"), today=_TODAY)

    assert result.refund_amount == Decimal("1000.00")
    assert result.penalty_amount == Decimal("0.00")


def test_a_non_refundable_rate_returns_nothing():
    result = refund_for(_Terms(refundable=False), Decimal("1000.00"), today=_TODAY)

    assert result.refund_amount == Decimal("0.00")
    assert result.penalty_amount == Decimal("1000.00")
    assert "non-refundable" in result.reason


def test_inside_the_free_window_the_fee_is_waived():
    # Check-in 20 June, 7 free days → free until 13 June; today is 1 June.
    result = refund_for(
        _Terms(free_cancellation_days=7, penalty_percent="30"),
        Decimal("1000.00"),
        today=_TODAY,
    )

    assert result.refund_amount == Decimal("1000.00")
    assert result.penalty_amount == Decimal("0.00")


def test_the_last_free_day_still_counts_as_free():
    result = refund_for(
        _Terms(free_cancellation_days=7, penalty_percent="30"),
        Decimal("1000.00"),
        today=date(2026, 6, 13),
    )

    assert result.penalty_amount == Decimal("0.00")


def test_outside_the_free_window_the_percentage_is_withheld():
    result = refund_for(
        _Terms(free_cancellation_days=7, penalty_percent="30"),
        Decimal("1000.00"),
        today=date(2026, 6, 14),
    )

    assert result.penalty_amount == Decimal("300.00")
    assert result.refund_amount == Decimal("700.00")


def test_a_fixed_fee_wins_over_a_percentage():
    result = refund_for(
        _Terms(penalty_percent="30", penalty_amount="120.00"),
        Decimal("1000.00"),
        today=_TODAY,
    )

    assert result.penalty_amount == Decimal("120.00")
    assert result.refund_amount == Decimal("880.00")


def test_the_fee_never_exceeds_what_was_actually_paid():
    """A deposit-only booking cannot be charged more than the deposit."""

    result = refund_for(
        _Terms(penalty_amount="900.00"), Decimal("200.00"), today=_TODAY
    )

    assert result.penalty_amount == Decimal("200.00")
    assert result.refund_amount == Decimal("0.00")


def test_an_unpaid_booking_owes_nothing_either_way():
    result = refund_for(_Terms(refundable=False), Decimal("0"), today=_TODAY)

    assert result.penalty_amount == Decimal("0.00")
    assert result.refund_amount == Decimal("0.00")


# --- the same rules, applied through an actual cancellation -----------------


async def _paid_booking(
    db: AsyncSession, owner, *, days_ahead: int = 30, **terms
) -> Booking:
    sanatorium = await make_sanatorium(db)
    room = await make_room(db, sanatorium=sanatorium)
    booking = Booking(
        user_id=owner.id,
        room_id=room.id,
        booking_type=BookingType.ROOM,
        check_in=date.today() + timedelta(days=days_ahead),
        check_out=date.today() + timedelta(days=days_ahead + 2),
        guests=1,
        status=BookingStatus.CONFIRMED,
        final_price=Decimal("1000.00"),
        currency="UZS",
        **terms,
    )
    db.add(booking)
    await db.flush()
    db.add(
        Payment(
            booking_id=booking.id,
            method=PaymentMethod.CASH,
            status=PaymentStatus.PAID,
            amount=Decimal("1000.00"),
            currency="UZS",
        )
    )
    await db.commit()
    await db.refresh(booking)
    return booking


def _service(db: AsyncSession) -> BookingService:
    return get_booking_service(db)


async def test_cancelling_a_refundable_stay_queues_the_whole_refund(
    db: AsyncSession,
):
    owner = await make_user(db, email="refund-full@test.com")
    booking = await _paid_booking(db, owner)

    cancelled = await _service(db).cancel(booking, owner)

    assert cancelled.status == BookingStatus.CANCELLED
    assert cancelled.cancellation_penalty_snapshot == Decimal("0.00")
    payment = cancelled.payments[0]
    assert payment.status == PaymentStatus.REFUND_PENDING
    assert payment.refund_amount == Decimal("1000.00")


async def test_cancelling_a_non_refundable_stay_keeps_the_money(db: AsyncSession):
    owner = await make_user(db, email="refund-none@test.com")
    booking = await _paid_booking(db, owner, refundable=False)

    cancelled = await _service(db).cancel(booking, owner)

    assert cancelled.cancellation_penalty_snapshot == Decimal("1000.00")
    payment = cancelled.payments[0]
    # Nothing is owed back, so this is not a refund waiting to be made —
    # the property keeps it and the finance report must not show a payout.
    assert payment.status == PaymentStatus.PAID
    assert payment.refund_amount == Decimal("0.00")


async def test_cancelling_late_withholds_the_fee(db: AsyncSession):
    owner = await make_user(db, email="refund-fee@test.com")
    # Arrival is in three days on a rate that is only free up to seven days
    # out, so the free window closed four days ago.
    booking = await _paid_booking(
        db,
        owner,
        days_ahead=3,
        free_cancellation_days=7,
        cancellation_penalty_percent=Decimal("25.00"),
    )

    cancelled = await _service(db).cancel(booking, owner)

    assert cancelled.cancellation_penalty_snapshot == Decimal("250.00")
    payment = cancelled.payments[0]
    assert payment.status == PaymentStatus.REFUND_PENDING
    assert payment.refund_amount == Decimal("750.00")
