"""Unit tests for the pricing/currency helpers (no DB needed)."""

from decimal import Decimal

from app.core.currency import CurrencyConverter


def _converter(target: str = "UZS", **rates: str) -> CurrencyConverter:
    """Build a converter from keyword rates like USD_UZS="12500"."""
    return CurrencyConverter(
        target, {pair: Decimal(value) for pair, value in rates.items()}
    )


class TestConvertToUzs:
    def test_already_uzs(self):
        result = _converter().convert(Decimal("100.00"), "UZS")
        assert result == Decimal("100.00")

    def test_usd_to_uzs(self):
        converter = _converter(USD_UZS="12500")
        result = converter.convert(Decimal("1.00"), "USD")
        assert result == Decimal("12500.00")

    def test_usd_no_rate_returns_none(self):
        assert _converter().convert(Decimal("1.00"), "USD") is None

    def test_rounding(self):
        converter = _converter(USD_UZS="12500.333333")
        result = converter.convert(Decimal("1.00"), "USD")
        assert result == Decimal("12500.33")


class TestConvertToUsd:
    def test_already_usd(self):
        result = _converter("USD").convert(Decimal("50.00"), "USD")
        assert result == Decimal("50.00")

    def test_uzs_to_usd(self):
        converter = _converter("USD", USD_UZS="12500")
        result = converter.convert(Decimal("12500.00"), "UZS")
        assert result == Decimal("1.00")

    def test_uzs_no_rate_returns_none(self):
        assert _converter("USD").convert(Decimal("12500.00"), "UZS") is None

    def test_rounding(self):
        # 10001 / 12500 = 0.800080... → 0.80
        converter = _converter("USD", USD_UZS="12500")
        result = converter.convert(Decimal("10001.00"), "UZS")
        assert result == Decimal("0.80")


class TestCrossRates:
    def test_usd_to_rub_via_uzs(self):
        # 1 USD = 12500 UZS, 1 RUB = 125 UZS → 1 USD = 100 RUB
        converter = _converter("RUB", USD_UZS="12500", RUB_UZS="125")
        result = converter.convert(Decimal("1.00"), "USD")
        assert result == Decimal("100.00")

    def test_explicit_target_overrides_display(self):
        converter = _converter("RUB", USD_UZS="12500", RUB_UZS="125")
        result = converter.convert(Decimal("1.00"), "USD", "UZS")
        assert result == Decimal("12500.00")

    def test_missing_target_rate_returns_none(self):
        converter = _converter("RUB", USD_UZS="12500")
        assert converter.convert(Decimal("1.00"), "USD") is None

    def test_none_amount_returns_none(self):
        converter = _converter("RUB", USD_UZS="12500", RUB_UZS="125")
        assert converter.convert(None, "USD") is None

    def test_case_insensitive_currencies(self):
        converter = CurrencyConverter("rub", {"usd_uzs": Decimal("12500")})
        assert converter.target == "RUB"
        result = converter.convert(Decimal("1.00"), "usd", "uzs")
        assert result == Decimal("12500.00")
