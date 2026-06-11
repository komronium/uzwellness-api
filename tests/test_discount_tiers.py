"""Unit tests for the discount-tier helpers (no DB)."""

from decimal import Decimal

from app.core.discount_tiers import best_tier_discount_percent, next_tier


_TIERS = [
    {"min_bookings": 10, "discount_percent": "5"},
    {"min_bookings": 25, "discount_percent": "10"},
    {"min_bookings": 50, "discount_percent": "15"},
]


class TestBestTierDiscountPercent:
    def test_empty_returns_zero(self):
        assert best_tier_discount_percent([], 100) == Decimal("0")

    def test_none_returns_zero(self):
        assert best_tier_discount_percent(None, 100) == Decimal("0")

    def test_below_first_tier_returns_zero(self):
        assert best_tier_discount_percent(_TIERS, 9) == Decimal("0")

    def test_picks_first_tier(self):
        assert best_tier_discount_percent(_TIERS, 10) == Decimal("5")

    def test_picks_middle_tier(self):
        assert best_tier_discount_percent(_TIERS, 25) == Decimal("10")

    def test_picks_highest_tier(self):
        assert best_tier_discount_percent(_TIERS, 100) == Decimal("15")

    def test_picks_best_when_tiers_unordered(self):
        unordered = [
            {"min_bookings": 50, "discount_percent": "15"},
            {"min_bookings": 10, "discount_percent": "5"},
        ]
        assert best_tier_discount_percent(unordered, 60) == Decimal("15")

    def test_malformed_tier_skipped(self):
        bad = [
            {"min_bookings": "garbage", "discount_percent": "10"},
            {"min_bookings": 10, "discount_percent": "5"},
        ]
        assert best_tier_discount_percent(bad, 100) == Decimal("5")

    def test_missing_key_skipped(self):
        bad = [{"min_bookings": 10}, {"min_bookings": 5, "discount_percent": "3"}]
        assert best_tier_discount_percent(bad, 100) == Decimal("3")


class TestNextTier:
    def test_empty_returns_none(self):
        assert next_tier([], 5) is None

    def test_below_first_tier(self):
        result = next_tier(_TIERS, 3)
        assert result == {
            "min_bookings": 10,
            "discount_percent": Decimal("5"),
            "bookings_to_unlock": 7,
        }

    def test_between_tiers(self):
        result = next_tier(_TIERS, 15)
        assert result == {
            "min_bookings": 25,
            "discount_percent": Decimal("10"),
            "bookings_to_unlock": 10,
        }

    def test_at_highest_tier_returns_none(self):
        assert next_tier(_TIERS, 50) is None

    def test_above_highest_tier_returns_none(self):
        assert next_tier(_TIERS, 200) is None

    def test_unordered_tiers_sorted_internally(self):
        unordered = [
            {"min_bookings": 50, "discount_percent": "15"},
            {"min_bookings": 10, "discount_percent": "5"},
            {"min_bookings": 25, "discount_percent": "10"},
        ]
        # 15 bookings → next is 25 (tier 10%)
        result = next_tier(unordered, 15)
        assert result is not None
        assert result["min_bookings"] == 25
