"""What the voucher prints, checked on the pure helpers behind it."""

from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.models.booking import BookingStatus, BookingType
from app.services.booking_voucher import (
    _LABELS,
    _Ctx,
    _cancellation_lines,
    _fmt_date,
    _fmt_money,
    _group_digits,
    _line_label,
    _print_jpeg,
    _status_key,
)
from app.services.cancellation_policy import refund_for
from tests.factories import make_png

CHECK_IN = date(2030, 5, 10)


def _booking(**kw):
    defaults = dict(
        status=BookingStatus.PENDING,
        booking_type=BookingType.ROOM,
        check_in=CHECK_IN,
        refundable=None,
        free_cancellation_days=None,
        cancellation_penalty_percent=None,
        cancellation_penalty_amount=None,
        final_price=Decimal("1000000"),
    )
    return SimpleNamespace(**{**defaults, **kw})


def _ctx(lang="en", currency="UZS", stay_name=None):
    return _Ctx(
        lang=lang,
        labels=_LABELS[lang],
        sanatorium=None,
        sanatorium_name="",
        invoice={"currency": currency, "nights": 7},
        stay_name=stay_name,
        photo=None,
    )


@pytest.mark.parametrize(
    ("status", "key"),
    [
        (BookingStatus.PENDING, "pending"),
        (BookingStatus.CONFIRMED, "confirmed"),
        (BookingStatus.COMPLETED, "completed"),
        (BookingStatus.CANCELLED, "cancelled"),
    ],
)
def test_status_banner_follows_booking_status(status, key) -> None:
    # A pending booking is unpaid: it must never be printed as confirmed.
    assert _status_key(_booking(status=status)) == key


def test_every_locale_has_the_same_labels() -> None:
    assert set(_LABELS["uz"]) == set(_LABELS["en"]) == set(_LABELS["ru"])


def test_non_refundable_says_nothing_comes_back() -> None:
    booking = _booking(refundable=False)
    assert _cancellation_lines(booking, _ctx()) == [_LABELS["en"]["non_refundable"]]
    assert refund_for(booking, Decimal("100"), today=CHECK_IN).refund_amount == 0


def test_free_window_then_percentage_penalty() -> None:
    booking = _booking(
        refundable=True,
        free_cancellation_days=3,
        cancellation_penalty_percent=Decimal("30.00"),
    )

    lines = _cancellation_lines(booking, _ctx())

    assert lines == [
        "Free cancellation until 7 May 2030.",
        "After that, 30% of the price is withheld.",
    ]
    # The printed date is the last day refund_for still refunds in full.
    deadline = CHECK_IN - timedelta(days=3)
    assert refund_for(booking, Decimal("100"), today=deadline).penalty_amount == 0
    after = deadline + timedelta(days=1)
    assert refund_for(booking, Decimal("100"), today=after).penalty_amount > 0


def test_no_terms_prints_full_refund_like_refund_for() -> None:
    booking = _booking()
    assert _cancellation_lines(booking, _ctx()) == [_LABELS["en"]["free"]]
    assert refund_for(booking, Decimal("100"), today=CHECK_IN).refund_amount == 100


def test_fixed_penalty_is_printed_in_local_money() -> None:
    booking = _booking(cancellation_penalty_amount=Decimal("250000"))
    assert _cancellation_lines(booking, _ctx("uz")) == [
        "Bekor qilinsa, 250 000 so'm ushlab qolinadi."
    ]


def test_money_formats() -> None:
    assert _fmt_money(Decimal("11900000.00"), "UZS", "uz") == "11 900 000 so'm"
    assert _fmt_money(Decimal("11900000"), "UZS", "ru") == "11 900 000 сум"
    assert _fmt_money(Decimal("11900000"), "UZS", "en") == "UZS 11,900,000"
    assert _fmt_money(Decimal("3200"), "USD", "ru") == "$3,200.00"


def test_dates_carry_the_year_in_each_language() -> None:
    day = date(2026, 10, 5)
    assert _fmt_date(day, "uz") == "5-oktyabr, 2026"
    assert _fmt_date(day, "ru") == "5 октября 2026"
    assert _fmt_date(day, "en") == "5 October 2026"


def test_reservation_number_is_grouped_for_reading_aloud() -> None:
    assert _group_digits("2610053172617351") == "2610 0531 7261 7351"


def test_package_line_shows_what_was_bought() -> None:
    item = {"description": "Room/program", "amount": Decimal("1")}
    package = _booking(booking_type=BookingType.PACKAGE)
    room = _booking(booking_type=BookingType.ROOM)

    assert (
        _line_label(item, _ctx(stay_name="7-night course"), package) == "7-night course"
    )
    assert _line_label(item, _ctx(stay_name="Deluxe"), room) == "Stay, 7 night(s)"


def test_photo_is_downscaled_for_email() -> None:
    big = make_png(3000, 2000)

    jpeg, width, height = _print_jpeg(big, 130, 85)

    # Embedded as a small JPEG at print size, not the full-size original.
    assert jpeg[:3] == b"\xff\xd8\xff"
    assert len(jpeg) < 60_000
    assert (round(width), round(height)) == (128, 85)
