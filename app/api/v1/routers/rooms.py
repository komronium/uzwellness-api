import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import CurrentUser, OptionalUser, require_roles
from app.models.user import User, UserRole
from app.schemas.room import (
    AvailabilityBulkCreate,
    AvailabilityRead,
    RoomCategoryCreate,
    RoomCategoryList,
    RoomCategoryRead,
    RoomCategoryUpdate,
)
from app.services.pricing import enrich_room
from app.services.room_search import RoomSearchService, get_room_search_service
from app.services.room_service import RoomService, get_room_service

router = APIRouter(prefix="/rooms", tags=["rooms"])

require_admin_or_above = require_roles(UserRole.ADMIN, UserRole.SUPER_ADMIN)


def _room_read(room, pricing: dict) -> RoomCategoryRead:
    return RoomCategoryRead.model_validate({**room.__dict__, **pricing})


@router.get("", response_model=RoomCategoryList)
async def list_rooms(
    current_user: OptionalUser,
    sanatorium_id: uuid.UUID = Query(...),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    rooms: RoomService = Depends(get_room_service),
) -> RoomCategoryList:
    items, total = await rooms.list_for_sanatorium(
        sanatorium_id,
        user=current_user,
        limit=limit,
        offset=offset,
        active_only=True,
    )
    usd_uzs = await rooms.get_usd_uzs_rate()
    return RoomCategoryList(
        items=[_room_read(r, enrich_room(r, usd_uzs)) for r in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/search", response_model=list[RoomCategoryRead])
async def search_rooms(
    check_in: date = Query(...),
    check_out: date = Query(...),
    guests: int = Query(default=1, ge=1),
    sanatorium_id: uuid.UUID | None = Query(default=None),
    search: RoomSearchService = Depends(get_room_search_service),
) -> list[RoomCategoryRead]:
    if check_out <= check_in:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="check_out must be after check_in",
        )
    results = await search.search(
        check_in=check_in,
        check_out=check_out,
        guests=guests,
        sanatorium_id=sanatorium_id,
    )
    return [_room_read(room, pricing) for room, pricing in results]


@router.get("/{room_id}", response_model=RoomCategoryRead)
async def get_room(
    room_id: uuid.UUID,
    rooms: RoomService = Depends(get_room_service),
) -> RoomCategoryRead:
    room = await rooms.get_by_id(room_id)
    if room is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")
    pricing = await rooms.enrich(room)
    return _room_read(room, pricing)


@router.post(
    "",
    response_model=RoomCategoryRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin_or_above)],
)
async def create_room(
    payload: RoomCategoryCreate,
    current_user: CurrentUser,
    rooms: RoomService = Depends(get_room_service),
) -> RoomCategoryRead:
    room = await rooms.create(payload, current_user)
    pricing = await rooms.enrich(room)
    return _room_read(room, pricing)


@router.patch("/{room_id}", response_model=RoomCategoryRead)
async def update_room(
    room_id: uuid.UUID,
    payload: RoomCategoryUpdate,
    current_user: CurrentUser,
    rooms: RoomService = Depends(get_room_service),
) -> RoomCategoryRead:
    if current_user.role not in (UserRole.ADMIN, UserRole.SUPER_ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )
    room = await rooms.get_by_id(room_id)
    if room is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")

    if current_user.role == UserRole.ADMIN:
        sanatorium = await rooms.get_sanatorium_for_room(room)
        if sanatorium is None or sanatorium.admin_user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not allowed to modify this room",
            )

    updated = await rooms.update(room, payload, current_user)
    pricing = await rooms.enrich(updated)
    return _room_read(updated, pricing)


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
