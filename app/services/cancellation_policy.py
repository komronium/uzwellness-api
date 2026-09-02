"""How much of a cancelled booking's money goes back to the guest.

The rate plan's cancellation terms are snapshotted onto the booking at
creation (``refundable``, ``free_cancellation_days``,
``cancellation_penalty_percent``, ``cancellation_penalty_amount``) and printed
on the voucher, so the guest has already been told these numbers. This module
is the one place that turns them into money; :meth:`BookingService.cancel`
applies the result.

The terms are read off the booking, never off the rate plan, so editing a rate
plan afterwards cannot change what an existing booking is owed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

_CENTS = Decimal("0.01")
_ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class RefundBreakdown:
    """What is owed back and what the property keeps, out of what was paid."""

    refund_amount: Decimal
    penalty_amount: Decimal
    reason: str


def free_cancellation_deadline(booking) -> date | None:
    """Last day the stay can be cancelled without a penalty, if there is one."""

    days = booking.free_cancellation_days
    if days is None:
        return None
    return booking.check_in - timedelta(days=days)


def refund_for(booking, paid_amount: Decimal, *, today: date) -> RefundBreakdown:
    """Split ``paid_amount`` into refund and penalty under the booking's terms.

    ``paid_amount`` is what actually reached us, so the penalty can never
    exceed it: a non-refundable stay that was never paid owes nothing, and a
    percentage penalty on a deposit-only booking is capped at the deposit.
    """

    paid = _money(paid_amount)
    if paid <= _ZERO:
        return RefundBreakdown(_ZERO, _ZERO, "Nothing was paid, so nothing is owed.")

    if booking.refundable is False:
        return RefundBreakdown(
            _ZERO,
            paid,
            "This rate is non-refundable, so the amount already paid is not returned.",
        )

    deadline = free_cancellation_deadline(booking)
    if deadline is not None and today <= deadline:
        return RefundBreakdown(
            paid,
            _ZERO,
            "Cancelled within the free cancellation period, so the full "
            "amount is refunded.",
        )

    penalty = _configured_penalty(booking)
    if penalty <= _ZERO:
        # A refundable rate with no penalty configured. This is also every
        # booking made without a rate plan, which is why the default has to be
        # a full refund rather than a guessed charge.
        return RefundBreakdown(paid, _ZERO, "The full amount is refunded.")

    penalty = min(penalty, paid)
    if deadline is None:
        reason = (
            "A cancellation fee applies to this rate, so it is deducted from "
            "the refund."
        )
    else:
        reason = (
            "Cancelled after the free cancellation period, so the "
            "cancellation fee is deducted from the refund."
        )
    return RefundBreakdown(_money(paid - penalty), penalty, reason)


def _configured_penalty(booking) -> Decimal:
    """The fee the booking's terms name — a fixed amount wins over a percent."""

    if booking.cancellation_penalty_amount is not None:
        return _money(booking.cancellation_penalty_amount)
    percent = booking.cancellation_penalty_percent
    if percent is None or percent <= _ZERO:
        return _ZERO
    # The percentage is of the stay's own total, not of what happens to have
    # been paid so far, so a part-paid booking is charged the same fee as a
    # fully paid one — capped at the payment by the caller.
    return _money(Decimal(booking.final_price) * Decimal(percent) / Decimal("100"))


def _money(value) -> Decimal:
    return Decimal(value or 0).quantize(_CENTS, ROUND_HALF_UP)
