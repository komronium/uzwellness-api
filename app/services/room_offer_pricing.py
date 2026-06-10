"""Money math for room-offer search.

Pure functions over already-loaded data: per-stay room totals, per-guest stay
option and treatment surcharges, promo discounts, and currency conversion.
Every amount is quantized to cents with ROUND_HALF_UP.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException, status

from app.core.pricing import (
    calculate_rate_plan_night_price,
    calculate_stay_total,
    convert_to_usd,
    convert_to_uzs,
)
from app.models.exchange_rate import ExchangeRate
from app.models.program import TreatmentProgram
from app.models.rate_plan import BoardType, RatePlan
from app.models.room import Room
from app.models.stay_option import SanatoriumStayOptionPrice, StayOptionGuestType
from app.schemas.room_offer import (
    RoomOfferGuest,
    RoomOfferGuestType,
    RoomOfferRequestedRoom,
)
from app.services.room_offer_guests import (
    GuestKey,
    GuestStayChoice,
    guest_option,
    guests,
    resolve_guest_program,
)

CENTS = Decimal("0.01")
ZERO = Decimal("0")

StayOptionPrices = dict[
    tuple[StayOptionGuestType, BoardType, bool], SanatoriumStayOptionPrice
]


def convert_currency(
    amount: Decimal,
    source_currency: str,
    target_currency: str,
    exchange_rate: ExchangeRate | None,
) -> Decimal | None:
    if source_currency == target_currency:
        return amount.quantize(CENTS, ROUND_HALF_UP)
    if target_currency == "UZS":
        return convert_to_uzs(amount, source_currency, exchange_rate)
    if target_currency == "USD":
        return convert_to_usd(amount, source_currency, exchange_rate)
    return None


def room_total(
    room: Room,
    rate_plan: RatePlan | None,
    dates: list[date],
    rooms_count: int,
) -> Decimal:
    if rate_plan is None:
        return (
            calculate_stay_total(room, dates, room.price_periods) * rooms_count
        ).quantize(CENTS, ROUND_HALF_UP)
    rules = {rule.date: rule for rule in rate_plan.date_rules}
    total = ZERO
    for target in dates:
        rule = rules.get(target)
        total += calculate_rate_plan_night_price(
            room,
            rate_plan,
            target,
            room.price_periods,
            selling_rate_override=rule.selling_rate if rule else None,
        )
    return (total * rooms_count).quantize(CENTS, ROUND_HALF_UP)


def stay_option_price(
    prices: StayOptionPrices,
    guest: RoomOfferGuest,
    option: GuestStayChoice,
) -> SanatoriumStayOptionPrice:
    guest_type = (
        StayOptionGuestType.ADULT
        if guest.type == RoomOfferGuestType.ADULT
        else StayOptionGuestType.CHILD
    )
    price = prices.get((guest_type, option.board, option.treatment_included))
    if price is None or not price.is_available:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Selected stay option is not available",
        )
    return price


def stay_option_total(
    *,
    prices: StayOptionPrices,
    requested_rooms: list[RoomOfferRequestedRoom],
    options: dict[GuestKey, GuestStayChoice],
    nights: int,
    exchange_rate: ExchangeRate | None,
    currency: str,
) -> Decimal:
    if not prices:
        return ZERO
    total = ZERO
    for room_index, requested_room in enumerate(requested_rooms):
        for guest in guests(requested_room):
            option = guest_option(options, room_index, guest.guest_index)
            price = stay_option_price(prices, guest, option)
            converted = convert_currency(
                price.price_delta, price.currency, currency, exchange_rate
            )
            if converted is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Exchange rate is required for stay option pricing",
                )
            total += converted * nights
    return total.quantize(CENTS, ROUND_HALF_UP)


def treatment_total(
    *,
    requested_rooms: list[RoomOfferRequestedRoom],
    options: dict[GuestKey, GuestStayChoice],
    treatments: list[TreatmentProgram],
    treatment_by_guest: dict[GuestKey, TreatmentProgram],
    exchange_rate: ExchangeRate | None,
    currency: str,
) -> Decimal:
    total = ZERO
    for room_index, requested_room in enumerate(requested_rooms):
        for guest in guests(requested_room):
            option = guest_option(options, room_index, guest.guest_index)
            program = resolve_guest_program(
                treatments, treatment_by_guest, room_index, guest, option
            )
            if program is None or program.price is None or program.currency is None:
                continue
            converted = convert_currency(
                program.price, program.currency, currency, exchange_rate
            )
            if converted is not None:
                total += converted
    return total.quantize(CENTS, ROUND_HALF_UP)


def original_total(subtotal: Decimal, rate_plan: RatePlan | None) -> Decimal | None:
    if rate_plan is None or not rate_plan.promo_percent:
        return None
    return subtotal


def apply_promo(subtotal: Decimal, rate_plan: RatePlan | None) -> Decimal:
    if rate_plan is None or not rate_plan.promo_percent:
        return subtotal
    return (subtotal * (1 - rate_plan.promo_percent / 100)).quantize(
        CENTS, ROUND_HALF_UP
    )
