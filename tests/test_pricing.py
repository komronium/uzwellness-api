"""Unit tests for the pricing service (no DB needed)."""
from decimal import Decimal

import pytest

from app.services.pricing import calculate_final_price, convert_to_uzs, convert_to_usd


def _rate(value: str):
    """Build a minimal fake ExchangeRate with just a .rate attribute."""

    class _FakeRate:
        rate = Decimal(value)

    return _FakeRate()


class TestCalculateFinalPrice:
    def test_zero_markup(self):
        assert calculate_final_price(Decimal("100.00"), Decimal("0")) == Decimal("100.00")

    def test_ten_percent_markup(self):
        assert calculate_final_price(Decimal("100.00"), Decimal("10")) == Decimal("110.00")

    def test_fractional_markup(self):
        result = calculate_final_price(Decimal("100.00"), Decimal("15.5"))
        assert result == Decimal("115.50")

    def test_rounding(self):
        # 100 * 1.333 = 133.3 → rounds to 133.30
        result = calculate_final_price(Decimal("100.00"), Decimal("33.3"))
        assert result == Decimal("133.30")

    def test_large_base_price(self):
        result = calculate_final_price(Decimal("500000.00"), Decimal("20"))
        assert result == Decimal("600000.00")


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
