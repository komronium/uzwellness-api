import math
import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.currency import CurrencyConverter
from app.core.pricing import enrich_room
from app.core.utils import date_range
from app.models.amenity import RoomAmenity
from app.models.availability import RoomAvailability
from app.models.room import Room
from app.models.sanatorium import Sanatorium, SanatoriumStatus


@dataclass(slots=True)
class RoomSearchHit:
    room: Room
    pricing: dict
    rooms_count_needed: int
    available: bool
    unavailable_reason: str | None


async def search_rooms(
    db: AsyncSession,
    converter: CurrencyConverter,
    *,
    check_in: date,
    check_out: date,
    guests: int,
    sanatorium_id: uuid.UUID | None = None,
) -> list[RoomSearchHit]:
    nights = (check_out - check_in).days
    if nights <= 0:
        return []

    all_dates = list(date_range(check_in, check_out))
    stmt = _room_search_statement(
        nights=nights, guests=guests, sanatorium_id=sanatorium_id
    )
    rooms = list((await db.scalars(stmt)).all())
    if not rooms:
        return []

    max_used_by_room = await _max_used_by_room(
        db, room_ids=[room.id for room in rooms], dates=all_dates
    )
    hits = [
        _room_hit(
            room,
            guests=guests,
            nights=nights,
            max_used=max_used_by_room,
            converter=converter,
        )
        for room in rooms
    ]
    if sanatorium_id is None:
        return [hit for hit in hits if hit.available]
    return hits


def _room_search_statement(
    *, nights: int, guests: int, sanatorium_id: uuid.UUID | None
):
    stmt = (
        select(Room)
        .join(Sanatorium, Room.sanatorium_id == Sanatorium.id)
        .where(
            Sanatorium.status == SanatoriumStatus.APPROVED,
            Room.is_active.is_(True),
            Room.deleted_at.is_(None),
        )
        .options(
            selectinload(Room.amenities),
            selectinload(Room.amenity_links).selectinload(RoomAmenity.amenity),
        )
        .order_by(Room.base_price.asc())
    )
    if sanatorium_id is not None:
        return stmt.where(Room.sanatorium_id == sanatorium_id)
    return stmt.where(
        Room.inventory_count >= 1,
        Room.capacity >= 1,
        Room.min_nights <= nights,
        Room.capacity * Room.inventory_count >= guests,
    )


async def _max_used_by_room(
    db: AsyncSession, *, room_ids: list[uuid.UUID], dates: list[date]
) -> dict[uuid.UUID, int]:
    usage_rows = (
        await db.execute(
            select(
                RoomAvailability.room_id,
                func.max(
                    RoomAvailability.units_blocked + RoomAvailability.units_booked
                ).label("max_used"),
            )
            .where(
                RoomAvailability.room_id.in_(room_ids),
                RoomAvailability.date.in_(dates),
            )
            .group_by(RoomAvailability.room_id)
        )
    ).all()
    return {row.room_id: int(row.max_used) for row in usage_rows}


def _room_hit(
    room: Room,
    *,
    guests: int,
    nights: int,
    max_used: dict[uuid.UUID, int],
    converter: CurrencyConverter,
) -> RoomSearchHit:
    rooms_needed = math.ceil(guests / room.capacity) if room.capacity > 0 else 0
    reason = _unavailable_reason(
        room,
        nights=nights,
        rooms_needed=rooms_needed,
        max_used=max_used.get(room.id, 0),
    )
    return RoomSearchHit(
        room=room,
        pricing=enrich_room(room, converter),
        rooms_count_needed=rooms_needed,
        available=reason is None,
        unavailable_reason=reason,
    )


def _unavailable_reason(
    room: Room, *, nights: int, rooms_needed: int, max_used: int
) -> str | None:
    free_worst_case = max(room.inventory_count - max_used, 0)
    if room.inventory_count < 1:
        return "no_inventory"
    if room.capacity < 1:
        return "no_capacity"
    if nights < room.min_nights:
        return "below_min_nights"
    if rooms_needed > room.inventory_count:
        return "exceeds_inventory"
    if rooms_needed > free_worst_case:
        return "insufficient_availability"
    return None
