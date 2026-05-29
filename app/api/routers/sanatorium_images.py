import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from app.api.deps import CurrentUser, not_found
from app.api.form_parsing import json_form
from app.api.routers.sanatorium_access import ensure_can_edit_sanatorium
from app.core.storage import StorageBackend, get_storage
from app.core.uploads import read_image_upload_as_webp
from app.schemas.sanatorium import SanatoriumImageRead, SanatoriumImageUpdate
from app.services.sanatorium_image_service import (
    SanatoriumImageService,
    get_sanatorium_image_service,
)
from app.services.sanatorium_service import (
    SanatoriumService,
    get_sanatorium_service,
)

router = APIRouter(prefix="/sanatoriums", tags=["Sanatoriums"])


@router.post(
    "/{sanatorium_id}/images",
    response_model=SanatoriumImageRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_image(
    sanatorium_id: uuid.UUID,
    current_user: CurrentUser,
    file: UploadFile = File(...),
    caption: str | None = Form(default=None, max_length=255),
    is_primary: bool = Form(default=False),
    is_360: bool = Form(default=False),
    category: str | None = Form(default=None, max_length=40),
    caption_i18n: str | None = Form(default=None),
    alt_text: str | None = Form(default=None),
    tags: str | None = Form(default=None),
    order: int = Form(default=0, ge=0),
    sanatoriums: SanatoriumService = Depends(get_sanatorium_service),
    images: SanatoriumImageService = Depends(get_sanatorium_image_service),
    storage: StorageBackend = Depends(get_storage),
) -> SanatoriumImageRead:
    sanatorium = await sanatoriums.get_by_id(sanatorium_id)
    if sanatorium is None:
        raise not_found("Sanatorium not found")
    ensure_can_edit_sanatorium(sanatorium, current_user)

    content, mime = await read_image_upload_as_webp(file)
    image = await images.add(
        sanatorium=sanatorium,
        content=content,
        content_type=mime,
        storage=storage,
        caption=caption,
        is_primary=is_primary,
        is_360=is_360,
        category=category,
        caption_i18n=json_form(caption_i18n, default={}),
        alt_text=json_form(alt_text, default={}),
        tags=json_form(tags, default=[]),
        order=order,
    )
    return SanatoriumImageRead.model_validate(image)


@router.patch(
    "/{sanatorium_id}/images/{image_id}",
    response_model=SanatoriumImageRead,
)
async def update_image(
    sanatorium_id: uuid.UUID,
    image_id: uuid.UUID,
    payload: SanatoriumImageUpdate,
    current_user: CurrentUser,
    sanatoriums: SanatoriumService = Depends(get_sanatorium_service),
    images: SanatoriumImageService = Depends(get_sanatorium_image_service),
) -> SanatoriumImageRead:
    image = await images.get(image_id)
    if image is None or image.sanatorium_id != sanatorium_id:
        raise not_found("Image not found")
    sanatorium = await sanatoriums.get_by_id(sanatorium_id)
    if sanatorium is None:
        raise not_found("Sanatorium not found")
    ensure_can_edit_sanatorium(sanatorium, current_user)
    updated = await images.update(
        image,
        is_primary=payload.is_primary,
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
    return SanatoriumImageRead.model_validate(updated)


@router.delete(
    "/{sanatorium_id}/images/{image_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_image(
    sanatorium_id: uuid.UUID,
    image_id: uuid.UUID,
    current_user: CurrentUser,
    sanatoriums: SanatoriumService = Depends(get_sanatorium_service),
    images: SanatoriumImageService = Depends(get_sanatorium_image_service),
    storage: StorageBackend = Depends(get_storage),
) -> None:
    image = await images.get(image_id)
    if image is None or image.sanatorium_id != sanatorium_id:
        raise not_found("Image not found")
    sanatorium = await sanatoriums.get_by_id(sanatorium_id)
    if sanatorium is None:
        raise not_found("Sanatorium not found")
    ensure_can_edit_sanatorium(sanatorium, current_user)
    await images.delete(image, storage)
