import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from app.api.deps import CurrentUser, not_found, require_roles
from app.api.form_parsing import json_form
from app.core.permissions import assert_sanatorium_access
from app.core.storage import StorageBackend, get_storage
from app.core.uploads import read_image_upload_as_webp
from app.models.user import UserRole
from app.schemas.room import RoomImageRead, RoomImageUpdate
from app.services.room_image_service import RoomImageService, get_room_image_service
from app.services.room_service import RoomService, get_room_service

router = APIRouter(prefix="/rooms", tags=["Rooms"])

require_admin_or_above = require_roles(UserRole.ADMIN, UserRole.SUPER_ADMIN)


@router.post(
    "/{room_id}/images",
    response_model=RoomImageRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin_or_above)],
)
async def upload_room_image(
    room_id: uuid.UUID,
    current_user: CurrentUser,
    file: UploadFile = File(...),
    caption: str | None = Form(default=None, max_length=255),
    is_primary: bool = Form(default=False),
    is_video: bool = Form(default=False),
    is_360: bool = Form(default=False),
    category: str | None = Form(default=None, max_length=40),
    caption_i18n: str | None = Form(default=None),
    alt_text: str | None = Form(default=None),
    tags: str | None = Form(default=None),
    order: int = Form(default=0, ge=0),
    rooms: RoomService = Depends(get_room_service),
    images: RoomImageService = Depends(get_room_image_service),
    storage: StorageBackend = Depends(get_storage),
) -> RoomImageRead:
    room = await rooms.get_by_id(room_id)
    if room is None:
        raise not_found("Room not found")
    await assert_sanatorium_access(
        rooms.db,
        room.sanatorium_id,
        current_user,
        action="manage this sanatorium's rooms",
    )
    content, mime = await read_image_upload_as_webp(file)
    image = await images.add(
        room=room,
        content=content,
        content_type=mime,
        storage=storage,
        caption=caption,
        is_primary=is_primary,
        is_video=is_video,
        is_360=is_360,
        category=category,
        caption_i18n=json_form(caption_i18n, default={}),
        alt_text=json_form(alt_text, default={}),
        tags=json_form(tags, default=[]),
        order=order,
    )
    return RoomImageRead.model_validate(image)


@router.patch(
    "/{room_id}/images/{image_id}",
    response_model=RoomImageRead,
    dependencies=[Depends(require_admin_or_above)],
)
async def update_room_image(
    room_id: uuid.UUID,
    image_id: uuid.UUID,
    payload: RoomImageUpdate,
    current_user: CurrentUser,
    rooms: RoomService = Depends(get_room_service),
    images: RoomImageService = Depends(get_room_image_service),
) -> RoomImageRead:
    image = await images.get(image_id)
    if image is None or image.room_id != room_id:
        raise not_found("Image not found")
    room = await rooms.get_by_id(room_id)
    if room is None:
        raise not_found("Room not found")
    await assert_sanatorium_access(
        rooms.db,
        room.sanatorium_id,
        current_user,
        action="manage this sanatorium's rooms",
    )
    updated = await images.update(
        image,
        is_primary=payload.is_primary,
        is_video=payload.is_video,
        is_360=payload.is_360,
        category=payload.category,
        order=payload.order,
        caption=payload.caption,
        caption_i18n=(
            payload.caption_i18n.model_dump(exclude_none=True)
            if payload.caption_i18n
            else None
        ),
        alt_text=(
            payload.alt_text.model_dump(exclude_none=True) if payload.alt_text else None
        ),
        tags=payload.tags,
    )
    return RoomImageRead.model_validate(updated)


@router.delete(
    "/{room_id}/images/{image_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin_or_above)],
)
async def delete_room_image(
    room_id: uuid.UUID,
    image_id: uuid.UUID,
    current_user: CurrentUser,
    rooms: RoomService = Depends(get_room_service),
    images: RoomImageService = Depends(get_room_image_service),
    storage: StorageBackend = Depends(get_storage),
) -> None:
    image = await images.get(image_id)
    if image is None or image.room_id != room_id:
        raise not_found("Image not found")
    room = await rooms.get_by_id(room_id)
    if room is None:
        raise not_found("Room not found")
    await assert_sanatorium_access(
        rooms.db,
        room.sanatorium_id,
        current_user,
        action="manage this sanatorium's rooms",
    )
    await images.delete(image, storage)
