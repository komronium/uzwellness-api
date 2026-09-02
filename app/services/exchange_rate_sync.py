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
_TWO = Decimal("0.01")


class CbuUnavailable(Exception):
    """CBU answered, but not with rates we can use."""


def parse_cbu_rates(items) -> list[ExchangeRateUpsert]:
    """Read CBU's daily feed, skipping entries we cannot make sense of.

    This is somebody else's JSON: a renamed field, a zero Nominal or a
    reformatted date must cost us that one currency, not the whole sync — and
    certainly not an unhandled exception on the admin's Sync button.
    """

    if not isinstance(items, list):
        raise CbuUnavailable(f"expected a JSON array, got {type(items).__name__}")
    if not items:
        raise CbuUnavailable("CBU returned an empty list of rates")
    wanted = set(settings.EXCHANGE_RATE_SYNC_CURRENCIES)
    parsed: list[ExchangeRateUpsert] = []
    skipped = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        ccy = item.get("Ccy")
        if ccy not in wanted:
            continue
        try:
            nominal = Decimal(str(item["Nominal"]))
            if nominal <= 0:
                raise ValueError(f"Nominal is {nominal}")
            rate = Decimal(str(item["Rate"])) / nominal
            valid_from = datetime.strptime(item["Date"], "%d.%m.%Y").replace(tzinfo=UTC)
            parsed.append(
                ExchangeRateUpsert(
                    pair=f"{ccy}_UZS",
                    rate=rate.quantize(_TWO, ROUND_HALF_UP),
                    valid_from=valid_from,
                )
            )
        except Exception:
            skipped += 1
            logger.warning("Skipping unusable CBU entry for %s: %r", ccy, item)
    if skipped and not parsed:
        # A feed that carries the currencies we track but none we could read
        # is a format change, not a quiet day — surface it to the caller.
        raise CbuUnavailable(f"every one of {skipped} tracked rate(s) was unreadable")
    return parsed


async def fetch_cbu_rates() -> list[ExchangeRateUpsert]:
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(CBU_RATES_URL)
        resp.raise_for_status()
        try:
            body = resp.json()
        except ValueError as exc:
            raise CbuUnavailable("CBU did not return JSON") from exc
        return parse_cbu_rates(body)


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
