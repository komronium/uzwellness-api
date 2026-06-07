from datetime import datetime
from zoneinfo import ZoneInfo

from app.models.booking import BookingType, generate_reservation_number


def test_reservation_number_encodes_date_type_channel(monkeypatch):
    monkeypatch.setattr("app.models.booking.secrets.randbelow", lambda _: 12_345_678)

    value = generate_reservation_number(
        booking_type=BookingType.PACKAGE,
        is_b2b=True,
        created_at=datetime(2026, 6, 7, 10, 30, tzinfo=ZoneInfo("Asia/Tashkent")),
    )

    assert value == "2606073212345678"
    assert value.isdigit()
    assert len(value) == 16


def test_reservation_number_uses_tashkent_date_for_aware_datetime(monkeypatch):
    monkeypatch.setattr("app.models.booking.secrets.randbelow", lambda _: 7)

    value = generate_reservation_number(
        booking_type=BookingType.ROOM,
        is_b2b=False,
        created_at=datetime(2026, 6, 6, 20, 30, tzinfo=ZoneInfo("UTC")),
    )

    assert value == "2606071100000007"
