from collections.abc import Sequence
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.models.exchange_rate import ExchangeRate
from app.models.room import Room, RoomPricePeriod

_TWO = Decimal("0.01")
_WEEKEND_DAYS = frozenset({4, 5})  # Fri, Sat


def calculate_final_price(base_price: Decimal, markup_percent: Decimal) -> Decimal:
    return (base_price * (1 + markup_percent / 100)).quantize(_TWO, ROUND_HALF_UP)


def effective_prices_for_date(
    room: Room,
    target: date,
    periods: Sequence[RoomPricePeriod] | None = None,
) -> tuple[Decimal, Decimal | None, Decimal | None]:
    if periods:
        for p in periods:
            if p.date_from <= target <= p.date_to:
                return (
                    p.base_price,
                    p.base_price_weekend,
                    p.discount_percent if p.discount_percent is not None else room.discount_percent,
                )
    return (room.base_price, room.base_price_weekend, room.discount_percent)


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


def calculate_stay_total(
    room: Room,
    dates: list[date],
    periods: Sequence[RoomPricePeriod] | None = None,
) -> Decimal:
    total = Decimal("0")
    for d in dates:
        base, weekend, discount = effective_prices_for_date(room, d, periods)
        total += calculate_night_price(
            base, weekend, room.markup_percent, discount, d.weekday() in _WEEKEND_DAYS,
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


def _price_block(
    room: Room,
    rate: ExchangeRate | None,
    *,
    discount: Decimal | None,
    weekend: bool,
) -> tuple[Decimal, Decimal | None, Decimal | None]:
    price = calculate_night_price(
        room.base_price, room.base_price_weekend, room.markup_percent, discount, weekend
    )
    return (
        price,
        convert_to_uzs(price, room.base_currency, rate),
        convert_to_usd(price, room.base_currency, rate),
    )


def enrich_room(room: Room, usd_uzs_rate: ExchangeRate | None) -> dict:
    discount = room.discount_percent
    weekday, weekday_uzs, weekday_usd = _price_block(
        room, usd_uzs_rate, discount=discount, weekend=False
    )
    result: dict = {
        "final_price": weekday,
        "final_price_uzs": weekday_uzs,
        "final_price_usd": weekday_usd,
    }
    if room.base_price_weekend is not None:
        weekend, weekend_uzs, weekend_usd = _price_block(
            room, usd_uzs_rate, discount=discount, weekend=True
        )
        result["final_price_weekend"] = weekend
        result["final_price_weekend_uzs"] = weekend_uzs
        result["final_price_weekend_usd"] = weekend_usd
    return result
