import math
import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pricing import enrich_room
from app.core.utils import date_range
from app.models.availability import RoomAvailability
from app.models.room import Room
from app.models.sanatorium import Sanatorium, SanatoriumStatus
from app.services.exchange_rate_service import ExchangeRateService


@dataclass(slots=True)
class RoomSearchHit:
    room: Room
    pricing: dict
    rooms_count_needed: int
    available: bool
    unavailable_reason: str | None


async def search_rooms(
    db: AsyncSession,
    rates: ExchangeRateService,
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
    stmt = (
        select(Room)
        .join(Sanatorium, Room.sanatorium_id == Sanatorium.id)
        .where(Sanatorium.status == SanatoriumStatus.APPROVED, Room.is_active.is_(True))
        .order_by(Room.base_price.asc())
    )
    if sanatorium_id is not None:
        stmt = stmt.where(Room.sanatorium_id == sanatorium_id)
    else:
        stmt = stmt.where(
            Room.inventory_count >= 1,
            Room.capacity >= 1,
            Room.min_nights <= nights,
            Room.capacity * Room.inventory_count >= guests,
        )

    rooms = list((await db.scalars(stmt)).all())
    if not rooms:
        return []

    usage_rows = (
        await db.execute(
            select(
                RoomAvailability.room_id,
                func.max(
                    RoomAvailability.units_blocked + RoomAvailability.units_booked
                ).label("max_used"),
            )
            .where(
                RoomAvailability.room_id.in_([r.id for r in rooms]),
                RoomAvailability.date.in_(all_dates),
            )
            .group_by(RoomAvailability.room_id)
        )
    ).all()
    max_used_by_room = {row.room_id: int(row.max_used) for row in usage_rows}

    rate = await rates.get_usd_uzs()
    hits: list[RoomSearchHit] = []
    for room in rooms:
        rooms_needed = math.ceil(guests / room.capacity) if room.capacity > 0 else 0
        used = max_used_by_room.get(room.id, 0)
        free_worst_case = max(room.inventory_count - used, 0)

        reason: str | None = None
        if room.inventory_count < 1:
            reason = "no_inventory"
        elif room.capacity < 1:
            reason = "no_capacity"
        elif nights < room.min_nights:
            reason = "below_min_nights"
        elif rooms_needed > room.inventory_count:
            reason = "exceeds_inventory"
        elif rooms_needed > free_worst_case:
            reason = "insufficient_availability"

        available = reason is None
        if not available and sanatorium_id is None:
            continue

        hits.append(
            RoomSearchHit(
                room=room,
                pricing=enrich_room(room, rate),
                rooms_count_needed=rooms_needed,
                available=available,
                unavailable_reason=reason,
            )
        )
    return hits
