"""Sync exchange rates from the Central Bank of Uzbekistan (CBU).

CBU publishes daily official rates as JSON; each item carries the currency
code, the rate in UZS and a Nominal (rate is per `Nominal` units).
"""

import asyncio
import logging
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.exchange_rate import RATE_SOURCE_CBU, ExchangeRate
from app.schemas.exchange_rate import ExchangeRateUpsert
from app.services.exchange_rate_service import ExchangeRateService

logger = logging.getLogger(__name__)

CBU_RATES_URL = "https://cbu.uz/uz/arkhiv-kursov-valyut/json/"
_SIX = Decimal("0.000001")


def parse_cbu_rates(items: list[dict]) -> list[ExchangeRateUpsert]:
    wanted = set(settings.EXCHANGE_RATE_SYNC_CURRENCIES)
    parsed: list[ExchangeRateUpsert] = []
    for item in items:
        ccy = item.get("Ccy")
        if ccy not in wanted:
            continue
        rate = Decimal(item["Rate"]) / Decimal(item["Nominal"])
        valid_from = datetime.strptime(item["Date"], "%d.%m.%Y").replace(tzinfo=UTC)
        parsed.append(
            ExchangeRateUpsert(
                pair=f"{ccy}_UZS",
                rate=rate.quantize(_SIX, ROUND_HALF_UP),
                valid_from=valid_from,
            )
        )
    return parsed


async def fetch_cbu_rates() -> list[ExchangeRateUpsert]:
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(CBU_RATES_URL)
        resp.raise_for_status()
        return parse_cbu_rates(resp.json())


async def sync_exchange_rates(db: AsyncSession) -> list[ExchangeRate]:
    payloads = await fetch_cbu_rates()
    service = ExchangeRateService(db)
    return [
        await service.upsert(payload, source=RATE_SOURCE_CBU) for payload in payloads
    ]


async def run_exchange_rate_sync_loop() -> None:
    from app.core.database import SessionLocal

    while True:
        try:
            async with SessionLocal() as db:
                rates = await sync_exchange_rates(db)
            logger.info("Synced %d exchange rates from CBU", len(rates))
        except Exception:
            logger.exception("Exchange rate sync from CBU failed")
        await asyncio.sleep(settings.EXCHANGE_RATE_SYNC_INTERVAL_HOURS * 3600)
