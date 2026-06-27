import uuid
from datetime import date

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.booking import BookingStatus, BookingType
from app.models.user import User
from app.services.finance_reports import (
    order_count_statement,
    order_item,
    orders_statement,
    summary_item,
    summary_statement,
)
from app.services.finance_rules import (
    assert_finance_role,
    can_see_internal_finance,
    finance_filters,
)


class FinanceService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def summary(
        self,
        actor: User,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        sanatorium_id: uuid.UUID | None = None,
        agent_id: uuid.UUID | None = None,
        is_b2b: bool | None = None,
        booking_status: BookingStatus | None = None,
        payment_status: str | None = None,
        booking_type: BookingType | None = None,
    ) -> dict:
        assert_finance_role(actor)
        filters = finance_filters(
            actor,
            date_from=date_from,
            date_to=date_to,
            sanatorium_id=sanatorium_id,
            agent_id=agent_id,
            is_b2b=is_b2b,
            booking_status=booking_status,
            booking_type=booking_type,
        )
        can_see_internal = can_see_internal_finance(actor)
        stmt = summary_statement(filters, payment_status=payment_status)
        rows = (await self.db.execute(stmt)).all()
        return {
            "items": [
                summary_item(row, can_see_internal=can_see_internal) for row in rows
            ]
        }

    async def orders(
        self,
        actor: User,
        *,
        limit: int,
        offset: int,
        date_from: date | None = None,
        date_to: date | None = None,
        sanatorium_id: uuid.UUID | None = None,
        agent_id: uuid.UUID | None = None,
        is_b2b: bool | None = None,
        booking_status: BookingStatus | None = None,
        payment_status: str | None = None,
        booking_type: BookingType | None = None,
    ) -> tuple[list[dict], int]:
        assert_finance_role(actor)
        filters = finance_filters(
            actor,
            date_from=date_from,
            date_to=date_to,
            sanatorium_id=sanatorium_id,
            agent_id=agent_id,
            is_b2b=is_b2b,
            booking_status=booking_status,
            booking_type=booking_type,
        )
        total = await self.db.scalar(
            order_count_statement(filters, payment_status=payment_status)
        )
        can_see_internal = can_see_internal_finance(actor)
        stmt = orders_statement(
            filters, limit=limit, offset=offset, payment_status=payment_status
        )
        rows = (await self.db.execute(stmt)).all()
        items = [order_item(row, can_see_internal=can_see_internal) for row in rows]
        return items, int(total or 0)


def get_finance_service(db: AsyncSession = Depends(get_db)) -> FinanceService:
    return FinanceService(db)
