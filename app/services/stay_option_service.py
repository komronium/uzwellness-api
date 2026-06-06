import uuid

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.stay_option import SanatoriumStayOptionPrice
from app.schemas.stay_option import StayOptionPriceBulkUpdate


class StayOptionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_for_sanatorium(
        self, sanatorium_id: uuid.UUID
    ) -> list[SanatoriumStayOptionPrice]:
        stmt = (
            select(SanatoriumStayOptionPrice)
            .where(SanatoriumStayOptionPrice.sanatorium_id == sanatorium_id)
            .order_by(
                SanatoriumStayOptionPrice.guest_type.asc(),
                SanatoriumStayOptionPrice.board.asc(),
                SanatoriumStayOptionPrice.treatment_included.desc(),
            )
        )
        return list((await self.db.scalars(stmt)).all())

    async def replace_for_sanatorium(
        self, sanatorium_id: uuid.UUID, payload: StayOptionPriceBulkUpdate
    ) -> list[SanatoriumStayOptionPrice]:
        self._assert_unique_options(payload)
        existing = {
            (item.guest_type, item.board, item.treatment_included): item
            for item in await self.list_for_sanatorium(sanatorium_id)
        }
        incoming_keys = set()
        for item in payload.items:
            key = (item.guest_type, item.board, item.treatment_included)
            incoming_keys.add(key)
            row = existing.get(key)
            if row is None:
                self.db.add(
                    SanatoriumStayOptionPrice(
                        sanatorium_id=sanatorium_id,
                        guest_type=item.guest_type,
                        board=item.board,
                        treatment_included=item.treatment_included,
                        price_delta=item.price_delta,
                        currency=item.currency,
                        is_available=item.is_available,
                    )
                )
                continue
            row.price_delta = item.price_delta
            row.currency = item.currency
            row.is_available = item.is_available

        for key, row in existing.items():
            if key not in incoming_keys:
                await self.db.delete(row)

        await self.db.commit()
        return await self.list_for_sanatorium(sanatorium_id)

    @staticmethod
    def _assert_unique_options(payload: StayOptionPriceBulkUpdate) -> None:
        seen = set()
        for item in payload.items:
            key = (item.guest_type, item.board, item.treatment_included)
            if key in seen:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Duplicate stay option price",
                )
            seen.add(key)


def get_stay_option_service(
    db: AsyncSession = Depends(get_db),
) -> StayOptionService:
    return StayOptionService(db)
