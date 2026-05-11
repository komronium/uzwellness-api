import uuid
from datetime import date, timedelta

from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.availability import RoomAvailability
from app.models.room import RoomCategory
from app.models.sanatorium import Sanatorium, SanatoriumStatus
from app.services.room_service import RoomService, get_room_service
from app.services.pricing import enrich_room


class RoomSearchService:
    def __init__(self, db: AsyncSession, rooms: RoomService) -> None:
        self.db = db
        self.rooms = rooms

    async def search(
        self,
        *,
        check_in: date,
        check_out: date,
        guests: int,
        sanatorium_id: uuid.UUID | None = None,
    ) -> list[tuple[RoomCategory, dict]]:
        nights = (check_out - check_in).days
        if nights <= 0:
            return []

        all_dates = [check_in + timedelta(days=i) for i in range(nights)]

        avail_subq = (
            select(
                RoomAvailability.room_category_id,
                func.count().label("covered_dates"),
            )
            .where(
                RoomAvailability.date.in_(all_dates),
                RoomAvailability.units_available >= 1,
            )
            .group_by(RoomAvailability.room_category_id)
            .subquery()
        )

        stmt = (
            select(RoomCategory)
            .join(Sanatorium, RoomCategory.sanatorium_id == Sanatorium.id)
            .join(avail_subq, RoomCategory.id == avail_subq.c.room_category_id)
            .where(
                Sanatorium.status == SanatoriumStatus.APPROVED,
                RoomCategory.is_active.is_(True),
                RoomCategory.capacity >= guests,
                RoomCategory.min_nights <= nights,
                avail_subq.c.covered_dates == nights,
            )
        )

        if sanatorium_id is not None:
            stmt = stmt.where(RoomCategory.sanatorium_id == sanatorium_id)

        stmt = stmt.order_by(RoomCategory.base_price.asc())
        rows = (await self.db.execute(stmt)).scalars().all()

        usd_uzs = await self.rooms.get_usd_uzs_rate()
        return [(room, enrich_room(room, usd_uzs)) for room in rows]


def get_room_search_service(
    db: AsyncSession = Depends(get_db),
    rooms: RoomService = Depends(get_room_service),
) -> RoomSearchService:
    return RoomSearchService(db, rooms)
