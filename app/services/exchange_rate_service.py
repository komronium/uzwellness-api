from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.currency import CurrencyConverter
from app.core.database import get_db
from app.models.exchange_rate import RATE_SOURCE_CBU, RATE_SOURCE_MANUAL, ExchangeRate
from app.schemas.exchange_rate import ExchangeRateUpsert

USD_UZS = "USD_UZS"


class ExchangeRateService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_all(self) -> list[ExchangeRate]:
        rows = await self.db.scalars(
            select(ExchangeRate).order_by(ExchangeRate.pair.asc())
        )
        return list(rows)

    async def get(self, pair: str) -> ExchangeRate | None:
        return await self.db.scalar(
            select(ExchangeRate).where(ExchangeRate.pair == pair)
        )

    async def get_usd_uzs(self) -> ExchangeRate | None:
        return await self.get(USD_UZS)

    async def get_converter(self, target: str = "UZS") -> CurrencyConverter:
        rows = await self.list_all()
        return CurrencyConverter(target, {row.pair: row.rate for row in rows})

    async def upsert(
        self,
        payload: ExchangeRateUpsert,
        *,
        source: str = RATE_SOURCE_MANUAL,
    ) -> ExchangeRate:
        existing = await self.get(payload.pair)
        if existing is not None:
            # A manual (admin-set) rate must survive automatic CBU syncs.
            if source == RATE_SOURCE_CBU and existing.source == RATE_SOURCE_MANUAL:
                return existing
            existing.rate = payload.rate
            existing.valid_from = payload.valid_from
            existing.source = source
            await self.db.commit()
            await self.db.refresh(existing)
            return existing

        rate = ExchangeRate(
            pair=payload.pair,
            rate=payload.rate,
            valid_from=payload.valid_from,
            source=source,
        )
        self.db.add(rate)
        await self.db.commit()
        await self.db.refresh(rate)
        return rate

    async def delete(self, pair: str) -> bool:
        existing = await self.get(pair)
        if existing is None:
            return False
        await self.db.delete(existing)
        await self.db.commit()
        return True


def get_exchange_rate_service(
    db: AsyncSession = Depends(get_db),
) -> ExchangeRateService:
    return ExchangeRateService(db)
