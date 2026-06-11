import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime

from fastapi import Depends, HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.currency import CurrencyConverter
from app.core.database import get_db
from app.core.db_utils import fetch_by_ids
from app.core.pagination import paginated
from app.core.permissions import assert_sanatorium_access
from app.core.pricing import enrich_room
from app.core.utils import merge_translation_fields
from app.models.amenity import Amenity, AmenityScope, RoomAmenity
from app.models.availability import RoomAvailability
from app.models.package import Package
from app.models.room import Room, SmokingPolicy, WindowPolicy
from app.models.sanatorium import Sanatorium, SanatoriumStatus
from app.models.user import User, UserRole
from app.schemas.room import RoomAmenityItem, RoomCreate, RoomOrderUpdate, RoomUpdate
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
        return await self._reload(room_id)

    async def list_for_sanatorium(
        self,
        sanatorium_id: uuid.UUID,
        *,
        user: User | None,
        limit: int,
        offset: int,
        is_active: bool | None = None,
        q: str | None = None,
        include_deleted: bool = False,
        deleted_only: bool = False,
    ) -> tuple[Sequence[Room], int]:
        stmt = (
            select(Room)
            .join(Sanatorium, Room.sanatorium_id == Sanatorium.id)
            .where(Room.sanatorium_id == sanatorium_id)
            .options(*_ROOM_LOAD_OPTIONS)
            .order_by(Room.display_order.asc(), Room.created_at.asc())
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
        if q and q.strip():
            pattern = f"%{q.strip()}%"
            stmt = stmt.where(
                or_(
                    Room.name["uz"].astext.ilike(pattern),
                    Room.name["ru"].astext.ilike(pattern),
                    Room.name["en"].astext.ilike(pattern),
                )
            )
        if is_privileged:
            if deleted_only:
                stmt = stmt.where(Room.deleted_at.is_not(None))
            elif not include_deleted:
                stmt = stmt.where(Room.deleted_at.is_(None))
            if is_active is not None:
                stmt = stmt.where(Room.is_active.is_(is_active))
        else:
            stmt = stmt.where(
                Room.is_active.is_(True),
                Room.deleted_at.is_(None),
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
        amenity_links = await self._build_amenity_links(
            _room_amenity_items(payload.amenity_items, payload.amenity_ids)
        )
        room = Room(
            sanatorium_id=payload.sanatorium_id,
            name=payload.name.model_dump(),
            description=payload.description.model_dump(exclude_none=True),
            amenity_links=amenity_links,
            size_sqm=payload.size_sqm,
            room_size_policy=payload.room_size_policy,
            floor=payload.floor,
            beds=[option.model_dump() for option in payload.beds],
            view=payload.view,
            smoking_allowed=_smoking_allowed(
                payload.smoking_policy, payload.smoking_allowed
            ),
            smoking_policy=_smoking_policy(
                payload.smoking_policy, payload.smoking_allowed
            ),
            window_policy=_window_policy(payload.window_policy, payload.room_features),
            window_description=payload.window_description,
            room_features=payload.room_features.model_dump(mode="json"),
            accommodation_type=payload.accommodation_type,
            gender_restriction=payload.gender_restriction,
            capacity=payload.capacity,
            max_adults=payload.max_adults,
            max_children=payload.max_children,
            max_child_rate_children=payload.max_child_rate_children,
            inventory_count=payload.inventory_count,
            room_advisories=payload.room_advisories,
            base_price=payload.base_price,
            base_price_weekend=payload.base_price_weekend,
            base_currency=payload.base_currency,
            min_nights=payload.min_nights,
            display_order=payload.display_order,
        )
        self.db.add(room)
        await self.db.commit()
        return await self._reload_required(room.id)

    async def update(self, room: Room, payload: RoomUpdate, user: User) -> Room:
        await assert_sanatorium_access(
            self.db, room.sanatorium_id, user, action="manage this sanatorium's rooms"
        )
        data = payload.model_dump(exclude_unset=True)
        amenity_ids = data.pop("amenity_ids", None)
        amenity_items = data.pop("amenity_items", None)

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
        if "room_features" in data and data["room_features"] is not None:
            data["room_features"] = payload.room_features.model_dump(mode="json")
            if "window_policy" not in data:
                data["window_policy"] = _window_policy(
                    payload.window_policy, payload.room_features
                )
        if "smoking_allowed" in data or "smoking_policy" in data:
            explicit_policy = data.get("smoking_policy")
            explicit_allowed = data.get("smoking_allowed", room.smoking_allowed)
            data["smoking_policy"] = _smoking_policy(explicit_policy, explicit_allowed)
            data["smoking_allowed"] = _smoking_allowed(
                explicit_policy, explicit_allowed
            )

        for key, value in data.items():
            setattr(room, key, value)
        if amenity_items is not None:
            room.amenity_links = await self._build_amenity_links(
                payload.amenity_items or []
            )
        elif amenity_ids is not None:
            room.amenity_links = await self._build_amenity_links(
                _room_amenity_items([], amenity_ids)
            )
        await self.db.commit()
        return await self._reload_required(room.id)

    async def _build_amenity_links(
        self, items: list[RoomAmenityItem]
    ) -> list[RoomAmenity]:
        if not items:
            return []
        amenities = await fetch_by_ids(
            self.db, Amenity, [item.amenity_id for item in items], label="amenity"
        )
        _assert_amenity_scope(amenities, allowed={AmenityScope.ROOM, AmenityScope.BOTH})
        return [
            RoomAmenity(
                amenity_id=item.amenity_id,
                status=item.status,
                cost=item.cost,
                is_available=item.is_available,
                details=item.details,
                display_order=item.display_order,
            )
            for item in items
        ]

    async def _reload_required(self, room_id: uuid.UUID) -> Room:
        room = await self._reload(room_id)
        if room is None:
            raise RuntimeError(f"Room {room_id} not found after write")
        return room

    async def _reload(self, room_id: uuid.UUID) -> Room | None:
        return await self.db.scalar(
            select(Room).where(Room.id == room_id).options(*_ROOM_LOAD_OPTIONS)
        )

    async def delete(self, room: Room, user: User) -> None:
        await assert_sanatorium_access(
            self.db, room.sanatorium_id, user, action="manage this sanatorium's rooms"
        )
        room.is_active = False
        room.deleted_at = datetime.now(UTC)
        await self.db.commit()

    async def order(self, payload: RoomOrderUpdate, user: User) -> None:
        await assert_sanatorium_access(
            self.db,
            payload.sanatorium_id,
            user,
            action="reorder this sanatorium's rooms",
        )
        ids = [item.room_id for item in payload.items]
        rooms = list(
            (
                await self.db.scalars(
                    select(Room).where(
                        Room.id.in_(ids),
                        Room.sanatorium_id == payload.sanatorium_id,
                        Room.deleted_at.is_(None),
                    )
                )
            ).all()
        )
        found = {room.id for room in rooms}
        missing = [room_id for room_id in ids if room_id not in found]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="All rooms must belong to the selected sanatorium",
            )
        order_by_id = {item.room_id: item.display_order for item in payload.items}
        for room in rooms:
            room.display_order = order_by_id[room.id]
        await self.db.commit()

    async def can_manage(self, room: Room, user: User | None) -> bool:
        if user is None:
            return False
        if user.role == UserRole.SUPER_ADMIN:
            return True
        if user.role != UserRole.ADMIN:
            return False
        return (
            await self.db.scalar(
                select(Sanatorium.id).where(
                    Sanatorium.id == room.sanatorium_id,
                    Sanatorium.admin_user_id == user.id,
                )
            )
        ) is not None

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

    async def enrich(self, room: Room, converter: CurrencyConverter) -> dict:
        return enrich_room(room, converter)

    async def search(
        self,
        *,
        converter: CurrencyConverter,
        check_in: date,
        check_out: date,
        guests: int,
        sanatorium_id: uuid.UUID | None = None,
    ) -> list["RoomSearchHit"]:
        return await search_rooms(
            self.db,
            converter,
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


_ROOM_LOAD_OPTIONS = (
    selectinload(Room.amenities),
    selectinload(Room.amenity_links).selectinload(RoomAmenity.amenity),
    selectinload(Room.images),
)


def _smoking_policy(
    policy: SmokingPolicy | None, smoking_allowed: bool | None
) -> SmokingPolicy:
    if policy is not None:
        return policy
    if smoking_allowed:
        return SmokingPolicy.SMOKING_PERMITTED
    return SmokingPolicy.NON_SMOKING


def _smoking_allowed(
    policy: SmokingPolicy | None, smoking_allowed: bool | None
) -> bool:
    if policy is not None:
        return policy != SmokingPolicy.NON_SMOKING
    return bool(smoking_allowed)


def _window_policy(policy: WindowPolicy | None, room_features) -> WindowPolicy | None:
    if policy is not None:
        return policy
    if room_features.has_window is True:
        return WindowPolicy.ALL_ROOMS_HAVE_WINDOWS
    if room_features.has_window is False:
        return WindowPolicy.NO_ROOMS_HAVE_WINDOWS
    return None


def _room_amenity_items(
    amenity_items: list[RoomAmenityItem], amenity_ids: list[uuid.UUID]
) -> list[RoomAmenityItem]:
    if amenity_items:
        return amenity_items
    return [RoomAmenityItem(amenity_id=amenity_id) for amenity_id in amenity_ids]


def _assert_amenity_scope(
    amenities: list[Amenity], *, allowed: set[AmenityScope]
) -> None:
    if any(item.scope not in allowed for item in amenities):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="One or more amenity IDs are not valid for this resource scope",
        )
