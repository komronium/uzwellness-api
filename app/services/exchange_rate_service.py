from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.room import ExchangeRate
from app.schemas.exchange_rate import ExchangeRateUpsert

USD_UZS = "USD_UZS"


class ExchangeRateService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_all(self) -> list[ExchangeRate]:
        stmt = select(ExchangeRate).order_by(ExchangeRate.pair.asc())
        return list((await self.db.execute(stmt)).scalars().all())

    async def get(self, pair: str) -> ExchangeRate | None:
        stmt = select(ExchangeRate).where(ExchangeRate.pair == pair)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_usd_uzs(self) -> ExchangeRate | None:
        return await self.get(USD_UZS)

    async def upsert(self, payload: ExchangeRateUpsert) -> ExchangeRate:
        existing = await self.get(payload.pair)
        if existing is not None:
            existing.rate = payload.rate
            existing.valid_from = payload.valid_from
            await self.db.commit()
            await self.db.refresh(existing)
            return existing

        rate = ExchangeRate(
            pair=payload.pair,
            rate=payload.rate,
            valid_from=payload.valid_from,
        )
        self.db.add(rate)
        await self.db.commit()
        await self.db.refresh(rate)
        return rate


def get_exchange_rate_service(
    db: AsyncSession = Depends(get_db),
) -> ExchangeRateService:
    return ExchangeRateService(db)
