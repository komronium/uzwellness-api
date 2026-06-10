"""Shared read-only aggregations over RoomAvailability usage.

Used by stay search, room-offer search, and the public availability calendar
so the "blocked + booked" math lives in exactly one place.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.availability import RoomAvailability
from app.models.room import Room

_USED = RoomAvailability.units_blocked + RoomAvailability.units_booked


async def max_used_by_room(
    db: AsyncSession, *, room_ids: list[uuid.UUID], dates: list[date]
) -> dict[uuid.UUID, int]:
    """Worst-case (max) units in use per room across the given dates."""
    if not room_ids or not dates:
        return {}
    rows = (
        await db.execute(
            select(
                RoomAvailability.room_id,
                func.max(_USED).label("max_used"),
            )
            .where(
                RoomAvailability.room_id.in_(room_ids),
                RoomAvailability.date.in_(dates),
            )
            .group_by(RoomAvailability.room_id)
        )
    ).all()
    return {row.room_id: int(row.max_used or 0) for row in rows}


async def used_per_date(
    db: AsyncSession,
    *,
    sanatorium_id: uuid.UUID,
    date_from: date,
    date_to: date,
) -> dict[date, int]:
    """Total units in use per day across a sanatorium's active rooms."""
    rows = (
        await db.execute(
            select(
                RoomAvailability.date,
                func.sum(_USED).label("used"),
            )
            .join(Room, RoomAvailability.room_id == Room.id)
            .where(
                Room.sanatorium_id == sanatorium_id,
                Room.is_active.is_(True),
                Room.deleted_at.is_(None),
                RoomAvailability.date >= date_from,
                RoomAvailability.date <= date_to,
            )
            .group_by(RoomAvailability.date)
        )
    ).all()
    return {row.date: int(row.used or 0) for row in rows}
