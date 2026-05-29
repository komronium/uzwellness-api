import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import assert_sanatorium_access
from app.core.utils import date_range
from app.models.availability import RoomAvailability
from app.models.room import Room
from app.models.user import User
from app.schemas.room import AvailabilityBlock


@dataclass(slots=True)
class RoomAvailabilityView:
    date: date
    inventory_count: int
    units_blocked: int
    units_booked: int
    units_available: int = field(init=False)

    def __post_init__(self) -> None:
        self.units_available = max(
            self.inventory_count - self.units_blocked - self.units_booked, 0
        )


class RoomAvailabilityService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def has_availability_map(
        self, room_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, bool]:
        if not room_ids:
            return {}
        rows = (
            await self.db.execute(
                select(Room.id, Room.inventory_count).where(Room.id.in_(room_ids))
            )
        ).all()
        return {row.id: row.inventory_count >= 1 for row in rows}

    async def get_availability(
        self, room: Room, date_from: date, date_to: date
    ) -> list[RoomAvailabilityView]:
        rows = {
            row.date: row
            for row in await self.db.scalars(
                select(RoomAvailability).where(
                    RoomAvailability.room_id == room.id,
                    RoomAvailability.date >= date_from,
                    RoomAvailability.date < date_to,
                )
            )
        }
        result: list[RoomAvailabilityView] = []
        for d in date_range(date_from, date_to):
            row = rows.get(d)
            result.append(
                RoomAvailabilityView(
                    date=d,
                    inventory_count=room.inventory_count,
                    units_blocked=row.units_blocked if row else 0,
                    units_booked=row.units_booked if row else 0,
                )
            )
        return result

    async def block_range(
        self, room: Room, payload: AvailabilityBlock, user: User
    ) -> list[RoomAvailabilityView]:
        if payload.date_from >= payload.date_to:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="date_from must be before date_to",
            )
        await assert_sanatorium_access(
            self.db, room.sanatorium_id, user, action="manage this room's availability"
        )
        all_dates = date_range(payload.date_from, payload.date_to)
        existing = {
            row.date: row
            for row in await self.db.scalars(
                select(RoomAvailability)
                .where(
                    RoomAvailability.room_id == room.id,
                    RoomAvailability.date.in_(all_dates),
                )
                .with_for_update()
            )
        }

        if payload.units_blocked > room.inventory_count:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"units_blocked ({payload.units_blocked}) exceeds "
                    f"inventory_count ({room.inventory_count})"
                ),
            )

        result: list[RoomAvailabilityView] = []
        for d in all_dates:
            row = existing.get(d)
            booked = row.units_booked if row else 0
            if payload.units_blocked + booked > room.inventory_count:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"units_blocked ({payload.units_blocked}) + booked "
                        f"({booked}) exceeds inventory_count "
                        f"({room.inventory_count}) on {d}"
                    ),
                )
            if row is None:
                row = RoomAvailability(
                    room_id=room.id,
                    date=d,
                    units_blocked=payload.units_blocked,
                    units_booked=0,
                )
                self.db.add(row)
            else:
                row.units_blocked = payload.units_blocked
            result.append(
                RoomAvailabilityView(
                    date=d,
                    inventory_count=room.inventory_count,
                    units_blocked=payload.units_blocked,
                    units_booked=booked,
                )
            )
        await self.db.commit()
        return result

    async def set_blocked_for_date(
        self,
        room: Room,
        target: date,
        units_blocked: int,
        user: User,
    ) -> RoomAvailabilityView:
        await assert_sanatorium_access(
            self.db, room.sanatorium_id, user, action="manage this room's availability"
        )
        if units_blocked > room.inventory_count:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"units_blocked ({units_blocked}) exceeds inventory_count "
                    f"({room.inventory_count})"
                ),
            )
        row = await self.db.scalar(
            select(RoomAvailability)
            .where(
                RoomAvailability.room_id == room.id,
                RoomAvailability.date == target,
            )
            .with_for_update()
        )
        if row is None:
            row = RoomAvailability(
                room_id=room.id,
                date=target,
                units_blocked=units_blocked,
                units_booked=0,
            )
            self.db.add(row)
            booked = 0
        else:
            if units_blocked + row.units_booked > room.inventory_count:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"units_blocked ({units_blocked}) + booked "
                        f"({row.units_booked}) exceeds inventory_count "
                        f"({room.inventory_count})"
                    ),
                )
            row.units_blocked = units_blocked
            booked = row.units_booked
        await self.db.commit()
        return RoomAvailabilityView(
            date=target,
            inventory_count=room.inventory_count,
            units_blocked=units_blocked,
            units_booked=booked,
        )


def get_room_availability_service(
    db: AsyncSession = Depends(get_db),
) -> RoomAvailabilityService:
    return RoomAvailabilityService(db)
