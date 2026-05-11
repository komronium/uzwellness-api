from decimal import ROUND_HALF_UP, Decimal

from app.models.room import ExchangeRate, RoomCategory

_TWO = Decimal("0.01")


def calculate_final_price(base_price: Decimal, markup_percent: Decimal) -> Decimal:
    return (base_price * (1 + markup_percent / 100)).quantize(_TWO, ROUND_HALF_UP)


def convert_to_uzs(amount: Decimal, currency: str, rate: ExchangeRate | None) -> Decimal | None:
    if currency == "UZS":
        return amount.quantize(_TWO, ROUND_HALF_UP)
    if rate is None:
        return None
    return (amount * rate.rate).quantize(_TWO, ROUND_HALF_UP)


def convert_to_usd(amount: Decimal, currency: str, rate: ExchangeRate | None) -> Decimal | None:
    if currency == "USD":
        return amount.quantize(_TWO, ROUND_HALF_UP)
    if rate is None:
        return None
    return (amount / rate.rate).quantize(_TWO, ROUND_HALF_UP)


def enrich_room(room: RoomCategory, usd_uzs_rate: ExchangeRate | None) -> dict:
    """Return pricing fields to attach to a RoomCategoryRead."""
    final = calculate_final_price(room.base_price, room.markup_percent)
    return {
        "final_price": final,
        "final_price_uzs": convert_to_uzs(final, room.base_currency, usd_uzs_rate),
        "final_price_usd": convert_to_usd(final, room.base_currency, usd_uzs_rate),
    }
