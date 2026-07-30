"""Turns a route + vehicle choice into the frozen numbers a transfer carries.

Used by both ways a transfer can be ordered — inline during booking checkout
and standalone afterwards — so the two never drift apart on pricing, currency
conversion or commission.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils import pick_locale
from app.models.transfer_location import TransferLocation
from app.models.transfer_request import TransferDirection, VehicleType
from app.models.user import User, UserRole
from app.services.exchange_rate_service import ExchangeRateService
from app.services.transfer_tariff_service import TransferTariffService

_CENTS = Decimal("0.01")


@dataclass(slots=True)
class PricedTransfer:
    tariff_id: uuid.UUID
    price: Decimal
    currency: str
    commission_percent: Decimal | None
    commission_amount: Decimal | None
    pickup_location: str
    dropoff_location: str


async def price_transfer(
    db: AsyncSession,
    tariffs: TransferTariffService,
    *,
    route_from_id: uuid.UUID,
    route_to_id: uuid.UUID,
    vehicle_type: VehicleType,
    direction: TransferDirection,
    target_currency: str | None = None,
    locale: str = "en",
) -> PricedTransfer:
    """Resolve the live tariff and freeze it.

    ``target_currency`` is the booking's currency for an in-checkout add-on:
    the amount is converted once, here, and stored converted so the single
    payment total stays reconcilable if the rate moves afterwards.
    """
    quote = await tariffs.quote(
        route_from_id=route_from_id,
        route_to_id=route_to_id,
        vehicle_type=vehicle_type,
        direction=direction,
    )

    price = quote.price
    currency = quote.currency
    if target_currency and target_currency.upper() != currency.upper():
        currency = target_currency.upper()
        price = await _convert(db, quote.price, quote.currency, currency)

    percent = await db.scalar(
        select(User.transfer_commission_percent)
        .where(User.role == UserRole.TRANSFER_ADMIN)
        .limit(1)
    )
    commission = None
    if percent is not None:
        commission = (price * Decimal(percent) / 100).quantize(_CENTS, ROUND_HALF_UP)

    pickup, dropoff = await _endpoint_names(db, route_from_id, route_to_id, locale)
    return PricedTransfer(
        tariff_id=quote.tariff_id,
        price=price.quantize(_CENTS, ROUND_HALF_UP),
        currency=currency,
        commission_percent=percent,
        commission_amount=commission,
        pickup_location=pickup,
        dropoff_location=dropoff,
    )


async def _convert(
    db: AsyncSession, amount: Decimal, source: str, target: str
) -> Decimal:
    converter = await ExchangeRateService(db).get_converter(target)
    converted = converter.convert(amount, source, target)
    if converted is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Exchange rate {source}→{target} is unavailable",
        )
    return converted


async def _endpoint_names(
    db: AsyncSession,
    route_from_id: uuid.UUID,
    route_to_id: uuid.UUID,
    locale: str,
) -> tuple[str, str]:
    rows = (
        await db.scalars(
            select(TransferLocation).where(
                TransferLocation.id.in_({route_from_id, route_to_id})
            )
        )
    ).all()
    names = {row.id: pick_locale(row.name, locale) for row in rows}
    return names.get(route_from_id, ""), names.get(route_to_id, "")
