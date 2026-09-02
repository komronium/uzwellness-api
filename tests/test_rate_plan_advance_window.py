"""The advance-booking window the search and the booking path now share.

It used to live only in ``RoomBookingFlow``, so ``POST /bookings`` refused a
rate that ``POST /bookings/room-offer`` happily sold — and the offer search
kept showing it.
"""

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

from app.services.rate_plan_rules import advance_window_violation, hours_phrase

_ARRIVAL = date(2026, 6, 20)


def _rule(*, min_advance=None, max_advance=None):
    return SimpleNamespace(min_advance_hours=min_advance, max_advance_hours=max_advance)


def _now(days_before: int) -> datetime:
    return datetime(2026, 6, 20, tzinfo=UTC) - timedelta(days=days_before)


def test_a_night_without_a_rule_is_always_bookable():
    assert advance_window_violation(None, _ARRIVAL, _now(1)) is None


def test_booking_too_close_to_arrival_is_refused():
    reason = advance_window_violation(_rule(min_advance=48), _ARRIVAL, _now(1))

    assert reason is not None
    assert "at least 2 days before arrival" in reason


def test_booking_just_outside_the_cutoff_is_allowed():
    assert advance_window_violation(_rule(min_advance=48), _ARRIVAL, _now(3)) is None


def test_booking_before_the_rate_opens_is_refused():
    reason = advance_window_violation(_rule(max_advance=24 * 30), _ARRIVAL, _now(60))

    assert reason is not None
    assert "no earlier than 30 days before arrival" in reason


def test_booking_once_the_rate_has_opened_is_allowed():
    assert (
        advance_window_violation(_rule(max_advance=24 * 30), _ARRIVAL, _now(10)) is None
    )


def test_lead_times_read_as_a_guest_would_say_them():
    assert hours_phrase(1) == "1 hour"
    assert hours_phrase(5) == "5 hours"
    assert hours_phrase(24) == "1 day"
    assert hours_phrase(48) == "2 days"
    # Not a whole number of days, so days would be a lie.
    assert hours_phrase(36) == "36 hours"
