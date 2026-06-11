import uuid
from datetime import date

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)

from app.api.deps import (
    ConverterDep,
    CurrentUser,
    IncludeTranslationsDep,
    LocaleDep,
    OptionalUser,
    not_found,
    require_roles,
)
from app.api.room_mapping import (
    room_admin_list,
    room_admin_read,
    room_public_list,
    room_public_read,
    room_search_result,
)
from app.core.pagination import Pagination
from app.models.user import UserRole
from app.schemas.room import (
    RoomAdminList,
    RoomAdminRead,
    RoomCreate,
    RoomList,
    RoomOrderUpdate,
    RoomRead,
    RoomSearchResult,
    RoomUpdate,
)
from app.services.room_service import RoomService, get_room_service

router = APIRouter(prefix="/rooms", tags=["Rooms"])

require_admin_or_above = require_roles(UserRole.ADMIN, UserRole.SUPER_ADMIN)


@router.get("", response_model=RoomList | RoomAdminList)
async def list_rooms(
    current_user: OptionalUser,
    locale: LocaleDep,
    include_translations: IncludeTranslationsDep,
    converter: ConverterDep,
    page: Pagination,
    sanatorium_id: uuid.UUID = Query(...),
    q: str | None = Query(default=None, max_length=120),
    is_active: bool | None = Query(
        default=None,
        description="Filter rooms by active status (staff only; ignored for guests).",
    ),
    include_deleted: bool = Query(
        default=False,
        description="Include soft-deleted rooms (staff only; ignored for guests).",
    ),
    deleted_only: bool = Query(
        default=False,
        description="Return only soft-deleted rooms (staff only; ignored for guests).",
    ),
    rooms: RoomService = Depends(get_room_service),
) -> RoomList | RoomAdminList:
    items, total = await rooms.list_for_sanatorium(
        sanatorium_id,
        user=current_user,
        limit=page.limit,
        offset=page.offset,
        is_active=is_active,
        q=q,
        include_deleted=include_deleted,
        deleted_only=deleted_only,
    )
    has_avail = await rooms.has_availability_map([r.id for r in items])
    if include_translations:
        return RoomAdminList(
            items=room_admin_list(
                list(items), converter=converter, availability=has_avail
            ),
            total=total,
            limit=page.limit,
            offset=page.offset,
        )
    return RoomList(
        items=room_public_list(
            list(items), locale=locale, converter=converter, availability=has_avail
        ),
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/search", response_model=list[RoomSearchResult])
async def search_rooms(
    locale: LocaleDep,
    converter: ConverterDep,
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
        converter=converter,
        check_in=check_in,
        check_out=check_out,
        guests=guests,
        sanatorium_id=sanatorium_id,
    )
    return [room_search_result(hit, locale=locale) for hit in hits]


@router.patch(
    "/order",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin_or_above)],
)
async def order_rooms(
    payload: RoomOrderUpdate,
    current_user: CurrentUser,
    rooms: RoomService = Depends(get_room_service),
) -> None:
    await rooms.order(payload, current_user)


@router.get("/{room_id}", response_model=RoomRead | RoomAdminRead)
async def get_room(
    room_id: uuid.UUID,
    current_user: OptionalUser,
    locale: LocaleDep,
    include_translations: IncludeTranslationsDep,
    converter: ConverterDep,
    rooms: RoomService = Depends(get_room_service),
) -> RoomRead | RoomAdminRead:
    room = await rooms.get_by_id(room_id)
    if room is None:
        raise not_found("Room not found")
    if room.deleted_at is not None and not await rooms.can_manage(room, current_user):
        raise not_found("Room not found")
    pricing = await rooms.enrich(room, converter)
    if include_translations:
        return room_admin_read(room, pricing)
    return room_public_read(room, pricing, locale=locale)


@router.post(
    "",
    response_model=RoomAdminRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin_or_above)],
)
async def create_room(
    payload: RoomCreate,
    current_user: CurrentUser,
    converter: ConverterDep,
    rooms: RoomService = Depends(get_room_service),
) -> RoomAdminRead:
    room = await rooms.create(payload, current_user)
    return room_admin_read(room, await rooms.enrich(room, converter))


@router.patch(
    "/{room_id}",
    response_model=RoomAdminRead,
    dependencies=[Depends(require_admin_or_above)],
)
async def update_room(
    room_id: uuid.UUID,
    payload: RoomUpdate,
    current_user: CurrentUser,
    converter: ConverterDep,
    rooms: RoomService = Depends(get_room_service),
) -> RoomAdminRead:
    room = await rooms.get_by_id(room_id)
    if room is None:
        raise not_found("Room not found")
    updated = await rooms.update(room, payload, current_user)
    return room_admin_read(updated, await rooms.enrich(updated, converter))


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
