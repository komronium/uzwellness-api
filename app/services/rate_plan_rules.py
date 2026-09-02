"""Rate-plan date rules that both the search and the booking path must agree on.

An offer the search shows must be bookable, and a rule the booking path
enforces must already have hidden the offer — otherwise the guest picks a room
and is refused at the last step. The advance-booking window lives here because
it is the one rule that used to be checked in only one of the two.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone


def hours_until_arrival(arrival: date, now: datetime) -> float:
    return (
        datetime.combine(arrival, time.min, tzinfo=timezone.utc) - now
    ).total_seconds() / 3600


def hours_phrase(hours: int) -> str:
    """Render a lead time the way a guest would say it: "2 days", not "48 hours"."""

    if hours >= 24 and hours % 24 == 0:
        days = hours // 24
        return f"{days} day" if days == 1 else f"{days} days"
    return f"{hours} hour" if hours == 1 else f"{hours} hours"


def advance_window_violation(arrival_rule, arrival: date, now: datetime) -> str | None:
    """Why this rate cannot be booked for that arrival yet, or ``None``.

    ``min_advance_hours`` is a cut-off ("no bookings inside 48 hours of
    arrival") and ``max_advance_hours`` an opening ("bookable from 90 days
    out"). Both are properties of the arrival night's rule only.
    """

    if arrival_rule is None:
        return None
    lead = hours_until_arrival(arrival, now)
    if (
        arrival_rule.min_advance_hours is not None
        and lead < arrival_rule.min_advance_hours
    ):
        return (
            "This rate must be booked at least "
            f"{hours_phrase(arrival_rule.min_advance_hours)} before arrival"
        )
    if (
        arrival_rule.max_advance_hours is not None
        and lead > arrival_rule.max_advance_hours
    ):
        return (
            "This rate opens no earlier than "
            f"{hours_phrase(arrival_rule.max_advance_hours)} before arrival"
        )
    return None
