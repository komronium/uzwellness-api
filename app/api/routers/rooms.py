import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import (
    CurrentUser,
    IncludeTranslationsDep,
    LocaleDep,
    OptionalUser,
    not_found,
    require_roles,
)
from app.core.pagination import Pagination
from app.core.pricing import enrich_room
from app.models.room import Room
from app.models.user import UserRole
from app.schemas.room import (
    AvailabilityBlock,
    AvailabilityRead,
    AvailabilityUpsert,
    RoomAdminList,
    RoomAdminRead,
    RoomCreate,
    RoomList,
    RoomRead,
    RoomSearchResult,
    RoomUpdate,
)
from app.services.room_service import RoomService, get_room_service

router = APIRouter(prefix="/rooms", tags=["rooms"])

require_admin_or_above = require_roles(UserRole.ADMIN, UserRole.SUPER_ADMIN)


def _public_room(
    room: Room,
    pricing: dict,
    *,
    locale: str,
    has_availability: bool | None = None,
) -> RoomRead:
    if has_availability is None:
        has_availability = room.is_active and room.inventory_count >= 1
    return RoomRead.from_obj(room, locale).model_copy(
        update={**pricing, "has_availability": has_availability}
    )


def _admin_room(
    room: Room,
    pricing: dict,
    *,
    has_availability: bool | None = None,
) -> RoomAdminRead:
    if has_availability is None:
        has_availability = room.is_active and room.inventory_count >= 1
    return RoomAdminRead.model_validate(room).model_copy(
        update={**pricing, "has_availability": has_availability}
    )


@router.get("", response_model=None)
async def list_rooms(
    current_user: OptionalUser,
    locale: LocaleDep,
    include_translations: IncludeTranslationsDep,
    page: Pagination,
    sanatorium_id: uuid.UUID = Query(...),
    is_active: bool | None = Query(
        default=None,
        description="Filter rooms by active status (staff only; ignored for guests).",
    ),
    rooms: RoomService = Depends(get_room_service),
) -> RoomList | RoomAdminList:
    items, total = await rooms.list_for_sanatorium(
        sanatorium_id,
        user=current_user,
        limit=page.limit,
        offset=page.offset,
        is_active=is_active,
    )
    rate = await rooms.rates.get_usd_uzs()
    has_avail = await rooms.has_availability_map([r.id for r in items])
    if include_translations:
        return RoomAdminList(
            items=[
                _admin_room(
                    r,
                    enrich_room(r, rate),
                    has_availability=has_avail.get(r.id, False),
                )
                for r in items
            ],
            total=total,
            limit=page.limit,
            offset=page.offset,
        )
    return RoomList(
        items=[
            _public_room(
                r,
                enrich_room(r, rate),
                locale=locale,
                has_availability=has_avail.get(r.id, False),
            )
            for r in items
        ],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/search", response_model=list[RoomSearchResult])
async def search_rooms(
    locale: LocaleDep,
    check_in: date = Query(...),
    check_out: date = Query(...),
    guests: int = Query(default=1, ge=1),
    sanatorium_id: uuid.UUID | None = Query(default=None),
    rooms: RoomService = Depends(get_room_service),
) -> list[RoomSearchResult]:
    if check_out <= check_in:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="check_out must be after check_in",
        )
    hits = await rooms.search(
        check_in=check_in,
        check_out=check_out,
        guests=guests,
        sanatorium_id=sanatorium_id,
    )
    results: list[RoomSearchResult] = []
    for hit in hits:
        base = _public_room(
            hit.room,
            hit.pricing,
            locale=locale,
            has_availability=hit.room.is_active and hit.room.inventory_count >= 1,
        )
        results.append(
            RoomSearchResult(
                **base.model_dump(),
                available=hit.available,
                rooms_count_needed=hit.rooms_count_needed,
                unavailable_reason=hit.unavailable_reason,
            )
        )
    return results


@router.get("/{room_id}", response_model=None)
async def get_room(
    room_id: uuid.UUID,
    locale: LocaleDep,
    include_translations: IncludeTranslationsDep,
    rooms: RoomService = Depends(get_room_service),
) -> RoomRead | RoomAdminRead:
    room = await rooms.get_by_id(room_id)
    if room is None:
        raise not_found("Room not found")
    pricing = await rooms.enrich(room)
    if include_translations:
        return _admin_room(room, pricing)
    return _public_room(room, pricing, locale=locale)


@router.post(
    "",
    response_model=RoomAdminRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin_or_above)],
)
async def create_room(
    payload: RoomCreate,
    current_user: CurrentUser,
    rooms: RoomService = Depends(get_room_service),
) -> RoomAdminRead:
    room = await rooms.create(payload, current_user)
    return _admin_room(room, await rooms.enrich(room))


@router.patch(
    "/{room_id}",
    response_model=RoomAdminRead,
    dependencies=[Depends(require_admin_or_above)],
)
async def update_room(
    room_id: uuid.UUID,
    payload: RoomUpdate,
    current_user: CurrentUser,
    rooms: RoomService = Depends(get_room_service),
) -> RoomAdminRead:
    room = await rooms.get_by_id(room_id)
    if room is None:
        raise not_found("Room not found")
    updated = await rooms.update(room, payload, current_user)
    return _admin_room(updated, await rooms.enrich(updated))


@router.delete(
    "/{room_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin_or_above)],
)
async def delete_room(
    room_id: uuid.UUID,
    current_user: CurrentUser,
    rooms: RoomService = Depends(get_room_service),
) -> None:
    room = await rooms.get_by_id(room_id)
    if room is None:
        raise not_found("Room not found")
    await rooms.delete(room, current_user)


@router.get("/{room_id}/availability", response_model=list[AvailabilityRead])
async def get_room_availability(
    room_id: uuid.UUID,
    date_from: date = Query(..., alias="from"),
    date_to: date = Query(..., alias="to"),
    rooms: RoomService = Depends(get_room_service),
) -> list[AvailabilityRead]:
    room = await rooms.get_by_id(room_id)
    if room is None:
        raise not_found("Room not found")
    rows = await rooms.get_availability(room, date_from, date_to)
    return [
        AvailabilityRead(
            date=r.date,
            inventory_count=r.inventory_count,
            units_blocked=r.units_blocked,
            units_booked=r.units_booked,
            units_available=r.units_available,
        )
        for r in rows
    ]


@router.post(
    "/{room_id}/availability/block",
    response_model=list[AvailabilityRead],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin_or_above)],
)
async def block_availability_range(
    room_id: uuid.UUID,
    payload: AvailabilityBlock,
    current_user: CurrentUser,
    rooms: RoomService = Depends(get_room_service),
) -> list[AvailabilityRead]:
    room = await rooms.get_by_id(room_id)
    if room is None:
        raise not_found("Room not found")
    rows = await rooms.block_range(room, payload, current_user)
    return [
        AvailabilityRead(
            date=r.date,
            inventory_count=r.inventory_count,
            units_blocked=r.units_blocked,
            units_booked=r.units_booked,
            units_available=r.units_available,
        )
        for r in rows
    ]


@router.patch(
    "/{room_id}/availability/{target_date}",
    response_model=AvailabilityRead,
    dependencies=[Depends(require_admin_or_above)],
)
async def upsert_room_availability(
    room_id: uuid.UUID,
    target_date: date,
    payload: AvailabilityUpsert,
    current_user: CurrentUser,
    rooms: RoomService = Depends(get_room_service),
) -> AvailabilityRead:
    room = await rooms.get_by_id(room_id)
    if room is None:
        raise not_found("Room not found")
    row = await rooms.set_blocked_for_date(
        room, target_date, payload.units_blocked, current_user
    )
    return AvailabilityRead(
        date=row.date,
        inventory_count=row.inventory_count,
        units_blocked=row.units_blocked,
        units_booked=row.units_booked,
        units_available=row.units_available,
    )
