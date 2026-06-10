"""Transactional guards shared by every room-booking path.

Both the classic booking flows (`booking_flows/`) and the room-offer booking
path reserve the same inventory; keeping these checks in one place ensures the
paths cannot drift apart in locking or error semantics.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.availability import RoomAvailability
from app.models.room import Room
from app.models.sanatorium import Sanatorium, SanatoriumStatus

ROOM_UNAVAILABLE_DETAIL = "Selected room is no longer available"


async def approved_sanatorium(db: AsyncSession, sanatorium_id) -> Sanatorium:
    sanatorium = await db.get(Sanatorium, sanatorium_id)
    if sanatorium is None or sanatorium.status != SanatoriumStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Sanatorium is not available for booking",
        )
    return sanatorium


async def lock_room(
    db: AsyncSession,
    room_id,
    *,
    load_price_periods: bool = False,
    detail: str = ROOM_UNAVAILABLE_DETAIL,
) -> Room:
    stmt = select(Room).where(Room.id == room_id).with_for_update(of=Room)
    if load_price_periods:
        stmt = stmt.options(selectinload(Room.price_periods))
    room = await db.scalar(stmt)
    if room is None or not room.is_active or room.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
    return room


async def reserve_units(
    db: AsyncSession, room: Room, *, dates: list, rooms_count: int
) -> None:
    if room.inventory_count < 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Room has no inventory",
        )
    existing = {
        row.date: row
        for row in await db.scalars(
            select(RoomAvailability)
            .where(
                RoomAvailability.room_id == room.id,
                RoomAvailability.date.in_(dates),
            )
            .with_for_update()
        )
    }
    for target in dates:
        row = existing.get(target)
        if row is None:
            db.add(
                RoomAvailability(
                    room_id=room.id,
                    date=target,
                    units_blocked=0,
                    units_booked=rooms_count,
                )
            )
            continue
        if row.units_blocked + row.units_booked + rooms_count > room.inventory_count:
            free = room.inventory_count - row.units_blocked - row.units_booked
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Only {max(free, 0)} unit(s) free on {target}, need {rooms_count}"
                ),
            )
        row.units_booked += rooms_count
