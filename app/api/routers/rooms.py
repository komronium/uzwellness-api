import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import CurrentUser, OptionalUser, require_roles
from app.core.pricing import enrich_room
from app.models.room import Room
from app.models.user import UserRole
from app.schemas.room import (
    AvailabilityBulkCreate,
    AvailabilityRead,
    RoomCreate,
    RoomList,
    RoomRead,
    RoomUpdate,
)
from app.services.room_service import RoomService, get_room_service

router = APIRouter(prefix="/rooms", tags=["rooms"])

require_admin_or_above = require_roles(UserRole.ADMIN, UserRole.SUPER_ADMIN)


def _with_pricing(room: Room, pricing: dict) -> RoomRead:
    return RoomRead.model_validate(room).model_copy(update=pricing)


def _pricing_flags(user) -> tuple[bool, bool]:
    if user is None:
        return False, False
    is_b2b = user.role == UserRole.AGENT
    include_b2b = user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN)
    return is_b2b, include_b2b


@router.get("", response_model=RoomList)
async def list_rooms(
    current_user: OptionalUser,
    sanatorium_id: uuid.UUID = Query(...),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    rooms: RoomService = Depends(get_room_service),
) -> RoomList:
    items, total = await rooms.list_for_sanatorium(
        sanatorium_id,
        user=current_user,
        limit=limit,
        offset=offset,
    )
    is_b2b, include_b2b = _pricing_flags(current_user)
    rate = await rooms.rates.get_usd_uzs()
    return RoomList(
        items=[
            _with_pricing(
                r, enrich_room(r, rate, is_b2b=is_b2b, include_b2b_price=include_b2b)
            )
            for r in items
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/search", response_model=list[RoomRead])
async def search_rooms(
    current_user: OptionalUser,
    check_in: date = Query(...),
    check_out: date = Query(...),
    guests: int = Query(default=1, ge=1),
    sanatorium_id: uuid.UUID | None = Query(default=None),
    rooms: RoomService = Depends(get_room_service),
) -> list[RoomRead]:
    if check_out <= check_in:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="check_out must be after check_in",
        )
    is_b2b, _ = _pricing_flags(current_user)
    results = await rooms.search(
        check_in=check_in,
        check_out=check_out,
        guests=guests,
        sanatorium_id=sanatorium_id,
        is_b2b=is_b2b,
    )
    return [_with_pricing(room, pricing) for room, pricing in results]


@router.get("/{room_id}", response_model=RoomRead)
async def get_room(
    room_id: uuid.UUID,
    current_user: OptionalUser,
    rooms: RoomService = Depends(get_room_service),
) -> RoomRead:
    room = await rooms.get_by_id(room_id)
    if room is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")
    is_b2b, include_b2b = _pricing_flags(current_user)
    pricing = await rooms.enrich(room, is_b2b=is_b2b, include_b2b_price=include_b2b)
    return _with_pricing(room, pricing)


@router.post(
    "",
    response_model=RoomRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin_or_above)],
)
async def create_room(
    payload: RoomCreate,
    current_user: CurrentUser,
    rooms: RoomService = Depends(get_room_service),
) -> RoomRead:
    room = await rooms.create(payload, current_user)
    return _with_pricing(room, await rooms.enrich(room))


@router.patch(
    "/{room_id}",
    response_model=RoomRead,
    dependencies=[Depends(require_admin_or_above)],
)
async def update_room(
    room_id: uuid.UUID,
    payload: RoomUpdate,
    current_user: CurrentUser,
    rooms: RoomService = Depends(get_room_service),
) -> RoomRead:
    room = await rooms.get_by_id(room_id)
    if room is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")
    updated = await rooms.update(room, payload, current_user)
    return _with_pricing(updated, await rooms.enrich(updated))


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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")
    rows = await rooms.get_availability(room, date_from, date_to)
    return [AvailabilityRead.model_validate(r) for r in rows]


@router.post(
    "/{room_id}/availability",
    response_model=list[AvailabilityRead],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin_or_above)],
)
async def bulk_create_availability(
    room_id: uuid.UUID,
    payload: AvailabilityBulkCreate,
    current_user: CurrentUser,
    rooms: RoomService = Depends(get_room_service),
) -> list[AvailabilityRead]:
    room = await rooms.get_by_id(room_id)
    if room is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")
    rows = await rooms.bulk_create_availability(room, payload, current_user)
    return [AvailabilityRead.model_validate(r) for r in rows]
