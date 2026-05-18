import uuid
from collections.abc import Sequence
from datetime import date

from fastapi import Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.pagination import paginated
from app.core.permissions import assert_sanatorium_access
from app.core.pricing import enrich_room
from app.core.utils import date_range, strip_none
from app.models.availability import RoomAvailability
from app.models.room import Room
from app.models.sanatorium import Sanatorium, SanatoriumStatus
from app.models.user import User, UserRole
from app.schemas.room import AvailabilityBlock, RoomCreate, RoomUpdate
from app.services.exchange_rate_service import (
    ExchangeRateService,
    get_exchange_rate_service,
)


class RoomAvailabilityView:
    """Plain-data view of an availability row, with computed units_available."""

    __slots__ = (
        "date",
        "inventory_count",
        "units_blocked",
        "units_booked",
        "units_available",
    )

    def __init__(
        self,
        *,
        d: date,
        inventory_count: int,
        units_blocked: int,
        units_booked: int,
    ) -> None:
        self.date = d
        self.inventory_count = inventory_count
        self.units_blocked = units_blocked
        self.units_booked = units_booked
        self.units_available = max(
            inventory_count - units_blocked - units_booked, 0
        )


class RoomSearchHit:
    """Search hit: a room plus its availability verdict for the queried range."""

    __slots__ = (
        "room",
        "pricing",
        "rooms_count_needed",
        "available",
        "unavailable_reason",
    )

    def __init__(
        self,
        *,
        room: Room,
        pricing: dict,
        rooms_count_needed: int,
        available: bool,
        unavailable_reason: str | None,
    ) -> None:
        self.room = room
        self.pricing = pricing
        self.rooms_count_needed = rooms_count_needed
        self.available = available
        self.unavailable_reason = unavailable_reason


class RoomService:
    def __init__(self, db: AsyncSession, rates: ExchangeRateService) -> None:
        self.db = db
        self.rates = rates

    async def get_by_id(self, room_id: uuid.UUID) -> Room | None:
        stmt = select(Room).where(Room.id == room_id)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def list_for_sanatorium(
        self,
        sanatorium_id: uuid.UUID,
        *,
        user: User | None,
        limit: int,
        offset: int,
        is_active: bool | None = None,
    ) -> tuple[Sequence[Room], int]:
        stmt = (
            select(Room)
            .join(Sanatorium, Room.sanatorium_id == Sanatorium.id)
            .where(Room.sanatorium_id == sanatorium_id)
            .order_by(Room.created_at.asc())
        )
        owns_target = False
        if user is not None and user.role == UserRole.ADMIN:
            owns_target = (
                await self.db.execute(
                    select(Sanatorium.id).where(
                        Sanatorium.id == sanatorium_id,
                        Sanatorium.admin_user_id == user.id,
                    )
                )
            ).scalar_one_or_none() is not None
        is_privileged = user is not None and (
            user.role == UserRole.SUPER_ADMIN or owns_target
        )
        if is_privileged:
            if is_active is not None:
                stmt = stmt.where(Room.is_active.is_(is_active))
        else:
            stmt = stmt.where(
                Room.is_active.is_(True),
                Sanatorium.status == SanatoriumStatus.APPROVED,
            )
        return await paginated(self.db, stmt, limit=limit, offset=offset)

    async def create(self, payload: RoomCreate, user: User) -> Room:
        await assert_sanatorium_access(
            self.db, payload.sanatorium_id, user, action="manage this sanatorium's rooms"
        )
        room = Room(
            sanatorium_id=payload.sanatorium_id,
            name=payload.name.model_dump(exclude_none=True),
            room_amenities=payload.room_amenities,
            capacity=payload.capacity,
            inventory_count=payload.inventory_count,
            base_price=payload.base_price,
            base_price_weekend=payload.base_price_weekend,
            base_currency=payload.base_currency,
            min_nights=payload.min_nights,
        )
        self.db.add(room)
        await self.db.commit()
        await self.db.refresh(room)
        return room

    async def update(self, room: Room, payload: RoomUpdate, user: User) -> Room:
        await assert_sanatorium_access(
            self.db, room.sanatorium_id, user, action="manage this sanatorium's rooms"
        )
        data = payload.model_dump(exclude_unset=True)

        if "markup_percent" in data and user.role != UserRole.SUPER_ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only super_admin can change markup_percent",
            )
        if "inventory_count" in data and data["inventory_count"] is not None:
            await self._assert_inventory_safe(room.id, data["inventory_count"])
        if "name" in data and data["name"] is not None:
            data["name"] = strip_none(data["name"])

        for field, value in data.items():
            setattr(room, field, value)
        await self.db.commit()
        await self.db.refresh(room)
        return room

    async def delete(self, room: Room, user: User) -> None:
        await assert_sanatorium_access(
            self.db, room.sanatorium_id, user, action="manage this sanatorium's rooms"
        )
        await self.db.delete(room)
        await self.db.commit()

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
            for row in (
                await self.db.execute(
                    select(RoomAvailability)
                    .where(
                        RoomAvailability.room_id == room.id,
                        RoomAvailability.date.in_(all_dates),
                    )
                    .with_for_update()
                )
            ).scalars().all()
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
                    d=d,
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
        row = (
            await self.db.execute(
                select(RoomAvailability)
                .where(
                    RoomAvailability.room_id == room.id,
                    RoomAvailability.date == target,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
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
            d=target,
            inventory_count=room.inventory_count,
            units_blocked=units_blocked,
            units_booked=booked,
        )

    async def has_availability_map(
        self, room_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, bool]:
        """True for each room whose inventory_count >= 1 (can be booked).

        With lazy materialization a room is implicitly open on every date
        as long as its inventory_count > 0; specific dates can still be
        blocked via RoomAvailability exception rows.
        """
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
        """Return per-day view for `[date_from, date_to)`, filling missing dates."""
        rows = {
            row.date: row
            for row in (
                await self.db.execute(
                    select(RoomAvailability).where(
                        RoomAvailability.room_id == room.id,
                        RoomAvailability.date >= date_from,
                        RoomAvailability.date < date_to,
                    )
                )
            ).scalars().all()
        }
        result: list[RoomAvailabilityView] = []
        for d in date_range(date_from, date_to):
            row = rows.get(d)
            result.append(
                RoomAvailabilityView(
                    d=d,
                    inventory_count=room.inventory_count,
                    units_blocked=row.units_blocked if row else 0,
                    units_booked=row.units_booked if row else 0,
                )
            )
        return result

    async def enrich(self, room: Room) -> dict:
        rate = await self.rates.get_usd_uzs()
        return enrich_room(room, rate)

    async def search(
        self,
        *,
        check_in: date,
        check_out: date,
        guests: int,
        sanatorium_id: uuid.UUID | None = None,
    ) -> list["RoomSearchHit"]:
        """Find rooms for a date range.

        - With `sanatorium_id`: returns ALL active rooms for that sanatorium,
          flagged available/unavailable so the UI can disable rows.
        - Without: returns only available rooms (cross-sanatorium browsing).

        Multi-unit aware: a room is "available" if it has enough units to
        cover ceil(guests / capacity) on every night in the range.
        """
        import math

        nights = (check_out - check_in).days
        if nights <= 0:
            return []

        all_dates = list(date_range(check_in, check_out))

        # 1. Candidate rooms — active, approved sanatorium
        stmt = (
            select(Room)
            .join(Sanatorium, Room.sanatorium_id == Sanatorium.id)
            .where(
                Sanatorium.status == SanatoriumStatus.APPROVED,
                Room.is_active.is_(True),
            )
            .order_by(Room.base_price.asc())
        )
        if sanatorium_id is not None:
            stmt = stmt.where(Room.sanatorium_id == sanatorium_id)
        rooms = list((await self.db.execute(stmt)).scalars().all())
        if not rooms:
            return []

        # 2. Per-(room, date) usage in one query, then collapse to per-room
        # worst-case usage across the requested nights.
        usage_rows = (
            await self.db.execute(
                select(
                    RoomAvailability.room_id,
                    func.max(
                        RoomAvailability.units_blocked
                        + RoomAvailability.units_booked
                    ).label("max_used"),
                )
                .where(
                    RoomAvailability.room_id.in_([r.id for r in rooms]),
                    RoomAvailability.date.in_(all_dates),
                )
                .group_by(RoomAvailability.room_id)
            )
        ).all()
        max_used_by_room: dict[uuid.UUID, int] = {
            row.room_id: int(row.max_used) for row in usage_rows
        }

        # 3. Per-room verdict
        rate = await self.rates.get_usd_uzs()
        hits: list[RoomSearchHit] = []
        for room in rooms:
            rooms_needed = (
                math.ceil(guests / room.capacity) if room.capacity > 0 else 0
            )
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
                continue  # cross-sanatorium browse hides unavailable rows

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

    async def _assert_inventory_safe(
        self, room_id: uuid.UUID, new_count: int
    ) -> None:
        """Block lowering inventory_count below any date's (blocked+booked)."""
        max_used = (
            await self.db.execute(
                select(
                    func.max(
                        RoomAvailability.units_blocked + RoomAvailability.units_booked
                    )
                ).where(RoomAvailability.room_id == room_id)
            )
        ).scalar_one_or_none()
        if max_used is not None and max_used > new_count:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Cannot lower inventory_count to {new_count}: at least one "
                    f"date already has {max_used} units in use (blocked + booked)"
                ),
            )


def get_room_service(
    db: AsyncSession = Depends(get_db),
    rates: ExchangeRateService = Depends(get_exchange_rate_service),
) -> RoomService:
    return RoomService(db, rates)
