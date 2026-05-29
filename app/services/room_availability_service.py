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
        self._assert_valid_range(payload)
        await assert_sanatorium_access(
            self.db, room.sanatorium_id, user, action="manage this room's availability"
        )
        all_dates = date_range(payload.date_from, payload.date_to)
        existing = await self._locked_rows(room, all_dates)
        self._assert_units_within_inventory(payload.units_blocked, room)

        result: list[RoomAvailabilityView] = []
        for d in all_dates:
            result.append(
                self._set_blocked(existing.get(d), room, d, payload.units_blocked)
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
        self._assert_units_within_inventory(units_blocked, room)
        row = await self.db.scalar(
            select(RoomAvailability)
            .where(
                RoomAvailability.room_id == room.id,
                RoomAvailability.date == target,
            )
            .with_for_update()
        )
        view = self._set_blocked(row, room, target, units_blocked)
        await self.db.commit()
        return view

    @staticmethod
    def _assert_valid_range(payload: AvailabilityBlock) -> None:
        if payload.date_from >= payload.date_to:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="date_from must be before date_to",
            )

    async def _locked_rows(
        self, room: Room, dates: list[date]
    ) -> dict[date, RoomAvailability]:
        rows = await self.db.scalars(
            select(RoomAvailability)
            .where(
                RoomAvailability.room_id == room.id,
                RoomAvailability.date.in_(dates),
            )
            .with_for_update()
        )
        return {row.date: row for row in rows}

    @staticmethod
    def _assert_units_within_inventory(units_blocked: int, room: Room) -> None:
        if units_blocked > room.inventory_count:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"units_blocked ({units_blocked}) exceeds inventory_count "
                    f"({room.inventory_count})"
                ),
            )

    def _set_blocked(
        self,
        row: RoomAvailability | None,
        room: Room,
        target: date,
        units_blocked: int,
    ) -> RoomAvailabilityView:
        booked = row.units_booked if row else 0
        self._assert_units_plus_booked(units_blocked, booked, room, target)
        if row is None:
            self.db.add(
                RoomAvailability(
                    room_id=room.id,
                    date=target,
                    units_blocked=units_blocked,
                    units_booked=0,
                )
            )
        else:
            row.units_blocked = units_blocked
        return RoomAvailabilityView(
            date=target,
            inventory_count=room.inventory_count,
            units_blocked=units_blocked,
            units_booked=booked,
        )

    @staticmethod
    def _assert_units_plus_booked(
        units_blocked: int, booked: int, room: Room, target: date
    ) -> None:
        if units_blocked + booked > room.inventory_count:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"units_blocked ({units_blocked}) + booked ({booked}) "
                    f"exceeds inventory_count ({room.inventory_count}) on {target}"
                ),
            )


def get_room_availability_service(
    db: AsyncSession = Depends(get_db),
) -> RoomAvailabilityService:
    return RoomAvailabilityService(db)
