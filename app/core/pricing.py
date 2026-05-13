from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.models.room import ExchangeRate, RoomCategory

_TWO = Decimal("0.01")
_WEEKEND_DAYS = frozenset({4, 5})  # Friday=4, Saturday=5 (peak days in Uzbek resorts)


def calculate_final_price(base_price: Decimal, markup_percent: Decimal) -> Decimal:
    return (base_price * (1 + markup_percent / 100)).quantize(_TWO, ROUND_HALF_UP)


def calculate_night_price(
    base_price: Decimal,
    base_price_weekend: Decimal | None,
    markup_percent: Decimal,
    discount_percent: Decimal | None,
    weekend: bool,
) -> Decimal:
    effective_base = base_price_weekend if weekend and base_price_weekend is not None else base_price
    after_markup = effective_base * (1 + markup_percent / 100)
    if discount_percent:
        after_markup = after_markup * (1 - discount_percent / 100)
    return after_markup.quantize(_TWO, ROUND_HALF_UP)


def calculate_stay_total(room: RoomCategory, dates: list[date]) -> Decimal:
    total = Decimal("0")
    for d in dates:
        total += calculate_night_price(
            room.base_price,
            room.base_price_weekend,
            room.markup_percent,
            room.discount_percent,
            d.weekday() in _WEEKEND_DAYS,
        )
    return total.quantize(_TWO, ROUND_HALF_UP)


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
    weekday_price = calculate_night_price(
        room.base_price, room.base_price_weekend, room.markup_percent, room.discount_percent, False
    )
    result: dict = {
        "final_price": weekday_price,
        "final_price_uzs": convert_to_uzs(weekday_price, room.base_currency, usd_uzs_rate),
        "final_price_usd": convert_to_usd(weekday_price, room.base_currency, usd_uzs_rate),
    }
    if room.base_price_weekend is not None:
        weekend_price = calculate_night_price(
            room.base_price, room.base_price_weekend, room.markup_percent, room.discount_percent, True
        )
        result["final_price_weekend"] = weekend_price
        result["final_price_weekend_uzs"] = convert_to_uzs(weekend_price, room.base_currency, usd_uzs_rate)
        result["final_price_weekend_usd"] = convert_to_usd(weekend_price, room.base_currency, usd_uzs_rate)
    return result
