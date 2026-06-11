import httpx
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import require_roles
from app.core.currency import DEFAULT_DISPLAY_CURRENCY, supported_display_currencies
from app.models.exchange_rate import RATE_SOURCE_CBU
from app.models.user import UserRole
from app.schemas.exchange_rate import (
    ExchangeRateCurrency,
    ExchangeRateCurrencyList,
    ExchangeRateRead,
    ExchangeRateUpsert,
)
from app.services.exchange_rate_service import (
    ExchangeRateService,
    get_exchange_rate_service,
)
from app.services.exchange_rate_sync import fetch_cbu_rates

router = APIRouter(prefix="/exchange-rates", tags=["Payments"])

require_super_admin = require_roles(UserRole.SUPER_ADMIN)


@router.get("", response_model=list[ExchangeRateRead])
async def list_exchange_rates(
    rates: ExchangeRateService = Depends(get_exchange_rate_service),
) -> list[ExchangeRateRead]:
    items = await rates.list_all()
    return [ExchangeRateRead.model_validate(r) for r in items]


@router.get("/currencies", response_model=ExchangeRateCurrencyList)
async def list_supported_currencies(
    rates: ExchangeRateService = Depends(get_exchange_rate_service),
) -> ExchangeRateCurrencyList:
    """Return display currencies for the frontend selector."""
    by_currency = {row.pair.split("_", 1)[0]: row for row in await rates.list_all()}
    currencies = [
        ExchangeRateCurrency(
            currency="UZS",
            rate_to_uzs=1,
            source="base",
            valid_from=None,
            is_available=True,
        )
    ]
    for currency in supported_display_currencies():
        if currency == "UZS":
            continue
        row = by_currency.get(currency)
        currencies.append(
            ExchangeRateCurrency(
                currency=currency,
                rate_to_uzs=row.rate if row is not None else None,
                source=row.source if row is not None else None,
                valid_from=row.valid_from if row is not None else None,
                is_available=row is not None,
            )
        )
    return ExchangeRateCurrencyList(
        default_currency=DEFAULT_DISPLAY_CURRENCY,
        currencies=currencies,
    )


@router.patch(
    "",
    response_model=ExchangeRateRead,
    dependencies=[Depends(require_super_admin)],
)
async def upsert_exchange_rate(
    payload: ExchangeRateUpsert,
    rates: ExchangeRateService = Depends(get_exchange_rate_service),
) -> ExchangeRateRead:
    """Manually override a rate. Marked `source=manual`, so the automatic
    CBU sync will not touch it; DELETE the pair to return to auto mode."""
    return ExchangeRateRead.model_validate(await rates.upsert(payload))


@router.delete(
    "/{pair}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_super_admin)],
)
async def delete_exchange_rate(
    pair: str,
    rates: ExchangeRateService = Depends(get_exchange_rate_service),
) -> None:
    """Remove a rate (e.g. a manual override; the next CBU sync re-creates
    synced pairs with the official rate)."""
    if not await rates.delete(pair.upper()):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Exchange rate not found"
        )


@router.post(
    "/sync",
    response_model=list[ExchangeRateRead],
    dependencies=[Depends(require_super_admin)],
)
async def sync_exchange_rates(
    rates: ExchangeRateService = Depends(get_exchange_rate_service),
) -> list[ExchangeRateRead]:
    """Pull today's official rates from the Central Bank of Uzbekistan."""
    try:
        payloads = await fetch_cbu_rates()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch exchange rates from CBU",
        ) from exc
    return [
        ExchangeRateRead.model_validate(await rates.upsert(p, source=RATE_SOURCE_CBU))
        for p in payloads
    ]
