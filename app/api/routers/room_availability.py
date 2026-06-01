import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, not_found, require_roles
from app.models.user import UserRole
from app.schemas.availability_calendar import AvailableAllotmentSet
from app.schemas.room import AvailabilityBlock, AvailabilityRead, AvailabilityUpsert
from app.services.room_availability_service import (
    RoomAvailabilityService,
    get_room_availability_service,
)
from app.services.room_service import RoomService, get_room_service

router = APIRouter(prefix="/rooms", tags=["Rooms"])

require_admin_or_above = require_roles(UserRole.ADMIN, UserRole.SUPER_ADMIN)


@router.get("/{room_id}/availability", response_model=list[AvailabilityRead])
async def get_room_availability(
    room_id: uuid.UUID,
    date_from: date = Query(..., alias="from"),
    date_to: date = Query(..., alias="to"),
    rooms: RoomService = Depends(get_room_service),
    availability: RoomAvailabilityService = Depends(get_room_availability_service),
) -> list[AvailabilityRead]:
    room = await rooms.get_by_id(room_id)
    if room is None:
        raise not_found("Room not found")
    rows = await availability.get_availability(room, date_from, date_to)
    return [_availability_read(row) for row in rows]


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
    availability: RoomAvailabilityService = Depends(get_room_availability_service),
) -> list[AvailabilityRead]:
    room = await rooms.get_by_id(room_id)
    if room is None:
        raise not_found("Room not found")
    rows = await availability.block_range(room, payload, current_user)
    return [_availability_read(row) for row in rows]


@router.patch(
    "/{room_id}/availability/allotment",
    response_model=list[AvailabilityRead],
    dependencies=[Depends(require_admin_or_above)],
)
async def set_available_allotment(
    room_id: uuid.UUID,
    payload: AvailableAllotmentSet,
    current_user: CurrentUser,
    rooms: RoomService = Depends(get_room_service),
    availability: RoomAvailabilityService = Depends(get_room_availability_service),
) -> list[AvailabilityRead]:
    room = await rooms.get_by_id(room_id)
    if room is None:
        raise not_found("Room not found")
    rows = await availability.set_available_allotment(room, payload, current_user)
    return [_availability_read(row) for row in rows]


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
    availability: RoomAvailabilityService = Depends(get_room_availability_service),
) -> AvailabilityRead:
    room = await rooms.get_by_id(room_id)
    if room is None:
        raise not_found("Room not found")
    row = await availability.set_blocked_for_date(
        room, target_date, payload.units_blocked, current_user
    )
    return _availability_read(row)


def _availability_read(row) -> AvailabilityRead:
    return AvailabilityRead(
        date=row.date,
        inventory_count=row.inventory_count,
        units_blocked=row.units_blocked,
        units_booked=row.units_booked,
        units_available=row.units_available,
    )
