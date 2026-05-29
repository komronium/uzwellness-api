import uuid
from collections.abc import Sequence
from datetime import date

from fastapi import Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.db_utils import fetch_by_ids
from app.core.pagination import paginated
from app.core.permissions import assert_sanatorium_access
from app.core.pricing import enrich_room
from app.core.utils import merge_translation_fields
from app.models.amenity import Amenity
from app.models.availability import RoomAvailability
from app.models.package import Package
from app.models.room import Room
from app.models.sanatorium import Sanatorium, SanatoriumStatus
from app.models.user import User, UserRole
from app.schemas.room import RoomCreate, RoomUpdate
from app.services.exchange_rate_service import (
    ExchangeRateService,
    get_exchange_rate_service,
)
from app.services.room_search import RoomSearchHit, search_rooms


class RoomService:
    def __init__(self, db: AsyncSession, rates: ExchangeRateService) -> None:
        self.db = db
        self.rates = rates

    async def get_by_id(self, room_id: uuid.UUID) -> Room | None:
        return await self.db.get(Room, room_id)

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
                await self.db.scalar(
                    select(Sanatorium.id).where(
                        Sanatorium.id == sanatorium_id,
                        Sanatorium.admin_user_id == user.id,
                    )
                )
            ) is not None
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
            self.db,
            payload.sanatorium_id,
            user,
            action="manage this sanatorium's rooms",
        )
        amenities = await fetch_by_ids(
            self.db, Amenity, payload.amenity_ids, label="amenity"
        )
        room = Room(
            sanatorium_id=payload.sanatorium_id,
            name=payload.name.model_dump(),
            description=payload.description.model_dump(exclude_none=True),
            amenities=amenities,
            size_sqm=payload.size_sqm,
            floor=payload.floor,
            beds=[option.model_dump() for option in payload.beds],
            view=payload.view,
            smoking_allowed=payload.smoking_allowed,
            room_features=payload.room_features.model_dump(mode="json"),
            capacity=payload.capacity,
            max_adults=payload.max_adults,
            max_children=payload.max_children,
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
        amenity_ids = data.pop("amenity_ids", None)

        if "markup_percent" in data and user.role != UserRole.SUPER_ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only super_admin can change markup_percent",
            )
        if "inventory_count" in data and data["inventory_count"] is not None:
            await self._assert_inventory_safe(room.id, data["inventory_count"])
        if "base_currency" in data and data["base_currency"] != room.base_currency:
            await self._assert_currency_change_safe(room.id, data["base_currency"])
        merge_translation_fields(room, data, ("name", "description"))

        for key, value in data.items():
            setattr(room, key, value)
        if amenity_ids is not None:
            room.amenities = await fetch_by_ids(
                self.db, Amenity, amenity_ids, label="amenity"
            )
        await self.db.commit()
        await self.db.refresh(room)
        return room

    async def delete(self, room: Room, user: User) -> None:
        await assert_sanatorium_access(
            self.db, room.sanatorium_id, user, action="manage this sanatorium's rooms"
        )
        await self.db.delete(room)
        await self.db.commit()

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
        return await search_rooms(
            self.db,
            self.rates,
            check_in=check_in,
            check_out=check_out,
            guests=guests,
            sanatorium_id=sanatorium_id,
        )

    async def _assert_inventory_safe(self, room_id: uuid.UUID, new_count: int) -> None:
        """Block lowering inventory_count below any date's (blocked+booked)."""
        max_used = await self.db.scalar(
            select(
                func.max(RoomAvailability.units_blocked + RoomAvailability.units_booked)
            ).where(RoomAvailability.room_id == room_id)
        )
        if max_used is not None and max_used > new_count:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Cannot lower inventory_count to {new_count}: at least one "
                    f"date already has {max_used} units in use (blocked + booked)"
                ),
            )

    async def _assert_currency_change_safe(
        self, room_id: uuid.UUID, new_currency: str
    ) -> None:
        # If any active package links to this room with a different currency,
        # changing room.base_currency would silently break the package's
        # currency invariant (enforced at package create/update time). Reject
        # the change here and force the admin to either reprice packages or
        # unlink them first.
        mismatched = await self.db.scalar(
            select(func.count(Package.id)).where(
                Package.room_id == room_id,
                Package.currency != new_currency,
            )
        )
        if mismatched:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Cannot change room currency to {new_currency}: "
                    f"{mismatched} linked package(s) use a different currency. "
                    "Update or unlink them first."
                ),
            )


def get_room_service(
    db: AsyncSession = Depends(get_db),
    rates: ExchangeRateService = Depends(get_exchange_rate_service),
) -> RoomService:
    return RoomService(db, rates)
