"""Unit tests for the pricing service (no DB needed)."""

from decimal import Decimal


from app.core.pricing import convert_to_uzs, convert_to_usd


def _rate(value: str):
    """Build a minimal fake ExchangeRate with just a .rate attribute."""

    class _FakeRate:
        rate = Decimal(value)

    return _FakeRate()


class TestConvertToUzs:
    def test_already_uzs(self):
        result = convert_to_uzs(Decimal("100.00"), "UZS", None)
        assert result == Decimal("100.00")

    def test_usd_to_uzs(self):
        rate = _rate("12500")
        result = convert_to_uzs(Decimal("1.00"), "USD", rate)
        assert result == Decimal("12500.00")

    def test_usd_no_rate_returns_none(self):
        assert convert_to_uzs(Decimal("1.00"), "USD", None) is None

    def test_rounding(self):
        rate = _rate("12500.333333")
        result = convert_to_uzs(Decimal("1.00"), "USD", rate)
        assert result == Decimal("12500.33")


class TestConvertToUsd:
    def test_already_usd(self):
        result = convert_to_usd(Decimal("50.00"), "USD", None)
        assert result == Decimal("50.00")

    def test_uzs_to_usd(self):
        rate = _rate("12500")
        result = convert_to_usd(Decimal("12500.00"), "UZS", rate)
        assert result == Decimal("1.00")

    def test_uzs_no_rate_returns_none(self):
        assert convert_to_usd(Decimal("12500.00"), "UZS", None) is None

    def test_rounding(self):
        # 10001 / 12500 = 0.800080... → 0.80
        rate = _rate("12500")
        result = convert_to_usd(Decimal("10001.00"), "UZS", rate)
        assert result == Decimal("0.80")
