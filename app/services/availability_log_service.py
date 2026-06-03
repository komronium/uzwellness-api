import uuid
from datetime import date, datetime
from collections.abc import Sequence

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.pagination import paginated
from app.core.permissions import assert_sanatorium_access
from app.models.availability_log import (
    AvailabilityLogCategory,
    AvailabilityOperationLog,
)
from app.models.user import User


class AvailabilityLogService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_for_sanatorium(
        self,
        sanatorium_id: uuid.UUID,
        user: User,
        *,
        room_id: uuid.UUID | None,
        rate_plan_id: uuid.UUID | None,
        category: AvailabilityLogCategory | None,
        check_in_from: date | None,
        check_in_to: date | None,
        operated_from: datetime | None,
        operated_to: datetime | None,
        limit: int,
        offset: int,
    ) -> tuple[Sequence[AvailabilityOperationLog], int]:
        await assert_sanatorium_access(
            self.db, sanatorium_id, user, action="view availability logs"
        )

        stmt = (
            select(AvailabilityOperationLog)
            .options(selectinload(AvailabilityOperationLog.operated_by))
            .where(AvailabilityOperationLog.sanatorium_id == sanatorium_id)
            .order_by(AvailabilityOperationLog.created_at.desc())
        )
        if room_id is not None:
            stmt = stmt.where(AvailabilityOperationLog.room_id == room_id)
        if rate_plan_id is not None:
            stmt = stmt.where(AvailabilityOperationLog.rate_plan_id == rate_plan_id)
        if category is not None:
            stmt = stmt.where(AvailabilityOperationLog.category == category)
        if check_in_from is not None:
            stmt = stmt.where(AvailabilityOperationLog.check_in_to >= check_in_from)
        if check_in_to is not None:
            stmt = stmt.where(AvailabilityOperationLog.check_in_from <= check_in_to)
        if operated_from is not None:
            stmt = stmt.where(AvailabilityOperationLog.created_at >= operated_from)
        if operated_to is not None:
            stmt = stmt.where(AvailabilityOperationLog.created_at <= operated_to)

        return await paginated(self.db, stmt, limit=limit, offset=offset)


def get_availability_log_service(
    db: AsyncSession = Depends(get_db),
) -> AvailabilityLogService:
    return AvailabilityLogService(db)
