from collections.abc import Sequence
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.core.currency import CurrencyConverter
from app.models.rate_plan import RatePlan
from app.models.room import Room, RoomPricePeriod

_TWO = Decimal("0.01")
WEEKEND_DAYS = frozenset({4, 5})


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
                    p.discount_percent
                    if p.discount_percent is not None
                    else room.discount_percent,
                )
    return (room.base_price, room.base_price_weekend, room.discount_percent)


def calculate_night_price(
    base_price: Decimal,
    base_price_weekend: Decimal | None,
    markup_percent: Decimal,
    discount_percent: Decimal | None,
    weekend: bool,
) -> Decimal:
    effective_base = (
        base_price_weekend if weekend and base_price_weekend is not None else base_price
    )
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
            base,
            weekend,
            room.markup_percent,
            discount,
            d.weekday() in WEEKEND_DAYS,
        )
    return total.quantize(_TWO, ROUND_HALF_UP)


def calculate_rate_plan_night_price(
    room: Room,
    rate_plan: RatePlan,
    target: date,
    periods: Sequence[RoomPricePeriod] | None = None,
    *,
    selling_rate_override: Decimal | None = None,
) -> Decimal:
    if selling_rate_override is not None:
        return selling_rate_override.quantize(_TWO, ROUND_HALF_UP)
    base, weekend_base, discount = effective_prices_for_date(room, target, periods)
    price = calculate_night_price(
        base,
        weekend_base,
        room.markup_percent,
        discount,
        target.weekday() in WEEKEND_DAYS,
    )
    if rate_plan.price_adjustment_percent is not None:
        price *= 1 + rate_plan.price_adjustment_percent / 100
    if rate_plan.board_optional and rate_plan.board_price is not None:
        price += rate_plan.board_price * (rate_plan.board_guests or room.capacity)
    return price.quantize(_TWO, ROUND_HALF_UP)


def _price_block(
    room: Room,
    converter: CurrencyConverter,
    *,
    discount: Decimal | None,
    weekend: bool,
) -> tuple[Decimal, Decimal | None, Decimal | None]:
    price = calculate_night_price(
        room.base_price, room.base_price_weekend, room.markup_percent, discount, weekend
    )
    return (
        price,
        converter.convert(price, room.base_currency, "UZS"),
        converter.convert(price, room.base_currency, "USD"),
    )


def enrich_room(room: Room, converter: CurrencyConverter) -> dict:
    discount = room.discount_percent
    weekday, weekday_uzs, weekday_usd = _price_block(
        room, converter, discount=discount, weekend=False
    )
    result: dict = {
        "final_price": weekday,
        "final_price_uzs": weekday_uzs,
        "final_price_usd": weekday_usd,
        "display_price": converter.convert(weekday, room.base_currency),
        "display_currency": converter.target,
    }
    if room.base_price_weekend is not None:
        weekend, weekend_uzs, weekend_usd = _price_block(
            room, converter, discount=discount, weekend=True
        )
        result["final_price_weekend"] = weekend
        result["final_price_weekend_uzs"] = weekend_uzs
        result["final_price_weekend_usd"] = weekend_usd
        result["display_price_weekend"] = converter.convert(weekend, room.base_currency)
    return result
