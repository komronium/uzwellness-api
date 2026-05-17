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
from app.core.utils import date_range, strip_none, today_tashkent
from app.models.availability import RoomAvailability
from app.models.room import Room
from app.models.sanatorium import Sanatorium, SanatoriumStatus
from app.models.user import User, UserRole
from app.schemas.room import AvailabilityBulkCreate, RoomCreate, RoomUpdate
from app.services.exchange_rate_service import (
    ExchangeRateService,
    get_exchange_rate_service,
)


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

    async def bulk_create_availability(
        self, room: Room, payload: AvailabilityBulkCreate, user: User
    ) -> list[RoomAvailability]:
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
                    select(RoomAvailability).where(
                        RoomAvailability.room_id == room.id,
                        RoomAvailability.date.in_(all_dates),
                    )
                )
            ).scalars().all()
        }

        result: list[RoomAvailability] = []
        for d in all_dates:
            if d in existing:
                if payload.overwrite:
                    row = existing[d]
                    row.units_total = payload.units_total
                    row.units_available = payload.units_total
                    result.append(row)
            else:
                row = RoomAvailability(
                    room_id=room.id,
                    date=d,
                    units_total=payload.units_total,
                    units_available=payload.units_total,
                )
                self.db.add(row)
                result.append(row)

        await self.db.commit()
        for row in result:
            await self.db.refresh(row)
        return result

    async def set_availability_for_date(
        self,
        room: Room,
        target: date,
        units_total: int,
        user: User,
    ) -> RoomAvailability:
        await assert_sanatorium_access(
            self.db, room.sanatorium_id, user, action="manage this room's availability"
        )
        if units_total < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="units_total must be >= 0",
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
                units_total=units_total,
                units_available=units_total,
            )
            self.db.add(row)
        else:
            booked = row.units_total - row.units_available
            if units_total < booked:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Cannot set units_total below current bookings ({booked})"
                    ),
                )
            row.units_total = units_total
            row.units_available = units_total - booked
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def availability_summary(
        self, room_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, date | None]:
        if not room_ids:
            return {}
        today = today_tashkent()
        stmt = (
            select(
                RoomAvailability.room_id,
                func.max(RoomAvailability.date).label("max_date"),
            )
            .where(
                RoomAvailability.room_id.in_(room_ids),
                RoomAvailability.date >= today,
                RoomAvailability.units_total > 0,
            )
            .group_by(RoomAvailability.room_id)
        )
        rows = (await self.db.execute(stmt)).all()
        result: dict[uuid.UUID, date | None] = {rid: None for rid in room_ids}
        for row in rows:
            result[row.room_id] = row.max_date
        return result

    async def get_availability(
        self, room: Room, date_from: date, date_to: date
    ) -> list[RoomAvailability]:
        stmt = (
            select(RoomAvailability)
            .where(
                RoomAvailability.room_id == room.id,
                RoomAvailability.date >= date_from,
                RoomAvailability.date < date_to,
            )
            .order_by(RoomAvailability.date.asc())
        )
        return list((await self.db.execute(stmt)).scalars().all())

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
    ) -> list[tuple[Room, dict]]:
        nights = (check_out - check_in).days
        if nights <= 0:
            return []

        all_dates = date_range(check_in, check_out)
        avail_subq = (
            select(
                RoomAvailability.room_id,
                func.count().label("covered_dates"),
            )
            .where(
                RoomAvailability.date.in_(all_dates),
                RoomAvailability.units_available >= 1,
            )
            .group_by(RoomAvailability.room_id)
            .subquery()
        )

        stmt = (
            select(Room)
            .join(Sanatorium, Room.sanatorium_id == Sanatorium.id)
            .join(avail_subq, Room.id == avail_subq.c.room_id)
            .where(
                Sanatorium.status == SanatoriumStatus.APPROVED,
                Room.is_active.is_(True),
                Room.capacity >= guests,
                Room.min_nights <= nights,
                avail_subq.c.covered_dates == nights,
            )
        )
        if sanatorium_id is not None:
            stmt = stmt.where(Room.sanatorium_id == sanatorium_id)

        rows = (
            await self.db.execute(stmt.order_by(Room.base_price.asc()))
        ).scalars().all()
        rate = await self.rates.get_usd_uzs()
        return [(room, enrich_room(room, rate)) for room in rows]


def get_room_service(
    db: AsyncSession = Depends(get_db),
    rates: ExchangeRateService = Depends(get_exchange_rate_service),
) -> RoomService:
    return RoomService(db, rates)
