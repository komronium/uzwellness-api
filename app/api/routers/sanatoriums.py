import uuid
import json
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)

from app.api.deps import (
    CurrentUser,
    IncludeTranslationsDep,
    LocaleDep,
    OptionalUser,
    not_found,
    require_roles,
)
from app.core.pagination import Pagination
from app.core.policies import SanatoriumPolicy
from app.core.storage import StorageBackend, detect_image_mime, get_storage
from app.core.uploads import read_upload
from app.models.sanatorium import PropertyType, SanatoriumStatus, WellnessCategory
from app.models.user import User, UserRole
from app.schemas.sanatorium import (
    SanatoriumAdminList,
    SanatoriumAdminRead,
    SanatoriumCreate,
    SanatoriumImageRead,
    SanatoriumImageUpdate,
    SanatoriumList,
    SanatoriumRead,
    SanatoriumUpdate,
)
from app.services.sanatorium_image_service import (
    SanatoriumImageService,
    get_sanatorium_image_service,
)
from app.services.sanatorium_service import (
    SanatoriumService,
    get_sanatorium_service,
)

router = APIRouter(prefix="/sanatoriums", tags=["sanatoriums"])

require_super_admin = require_roles(UserRole.SUPER_ADMIN)
require_admin_or_above = require_roles(UserRole.ADMIN, UserRole.SUPER_ADMIN)


def _json_form(value: str | None, *, default):
    if value is None or value == "":
        return default
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON form field",
        ) from exc
    if not isinstance(parsed, type(default)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="JSON form field has invalid type",
        )
    return parsed


def _ensure_can_edit(sanatorium, user: User) -> None:
    if not SanatoriumPolicy.can_edit(sanatorium, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not allowed to modify this sanatorium",
        )


SortField = Literal[
    "name", "-name", "stars", "-stars", "rating", "-rating", "created_at", "-created_at"
]


@router.get("", response_model=SanatoriumList | SanatoriumAdminList)
async def list_sanatoriums(
    current_user: OptionalUser,
    locale: LocaleDep,
    include_translations: IncludeTranslationsDep,
    page: Pagination,
    sanatoriums: SanatoriumService = Depends(get_sanatorium_service),
    city: str | None = Query(default=None, max_length=120),
    region_id: uuid.UUID | None = Query(default=None),
    destination_id: uuid.UUID | None = Query(default=None),
    status_filter: SanatoriumStatus | None = Query(default=None, alias="status"),
    stars: int | None = Query(default=None, ge=1, le=5),
    min_rating: Decimal | None = Query(default=None, ge=0, le=5),
    q: str | None = Query(default=None, max_length=200),
    sort: SortField = Query(default="-created_at"),
    amenity_ids: Annotated[list[uuid.UUID] | None, Query()] = None,
    treatment_focus: str | None = Query(default=None, max_length=60),
    property_type: PropertyType | None = Query(default=None),
    wellness_category: WellnessCategory | None = Query(default=None),
) -> SanatoriumList | SanatoriumAdminList:
    items, total = await sanatoriums.list_for_user(
        user=current_user,
        limit=page.limit,
        offset=page.offset,
        city=city,
        region_id=region_id,
        destination_id=destination_id,
        status_filter=status_filter,
        stars=stars,
        min_rating=min_rating,
        q=q,
        sort=sort,
        locale=locale,
        amenity_ids=amenity_ids,
        treatment_focus=treatment_focus,
        property_type=property_type,
        wellness_category=wellness_category,
    )
    if include_translations:
        return SanatoriumAdminList(
            items=[SanatoriumAdminRead.model_validate(s) for s in items],
            total=total,
            limit=page.limit,
            offset=page.offset,
        )
    return SanatoriumList(
        items=[SanatoriumRead.from_obj(s, locale) for s in items],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/{sanatorium_id}", response_model=SanatoriumRead | SanatoriumAdminRead)
async def get_sanatorium(
    sanatorium_id: uuid.UUID,
    current_user: OptionalUser,
    locale: LocaleDep,
    include_translations: IncludeTranslationsDep,
    sanatoriums: SanatoriumService = Depends(get_sanatorium_service),
) -> SanatoriumRead | SanatoriumAdminRead:
    sanatorium = await sanatoriums.get_visible(sanatorium_id, current_user)
    if sanatorium is None:
        raise not_found("Sanatorium not found")
    if include_translations:
        return SanatoriumAdminRead.model_validate(sanatorium)
    return SanatoriumRead.from_obj(sanatorium, locale)


@router.post(
    "",
    response_model=SanatoriumAdminRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_sanatorium(
    payload: SanatoriumCreate,
    current_user: User = Depends(require_admin_or_above),
    sanatoriums: SanatoriumService = Depends(get_sanatorium_service),
) -> SanatoriumAdminRead:
    # Admins always own the sanatorium they create; only super_admin may
    # explicitly assign it to a different admin.
    if current_user.role == UserRole.ADMIN:
        payload = payload.model_copy(update={"admin_user_id": current_user.id})
    sanatorium = await sanatoriums.create(payload)
    return SanatoriumAdminRead.model_validate(sanatorium)


@router.patch("/{sanatorium_id}", response_model=SanatoriumAdminRead)
async def update_sanatorium(
    sanatorium_id: uuid.UUID,
    payload: SanatoriumUpdate,
    current_user: CurrentUser,
    sanatoriums: SanatoriumService = Depends(get_sanatorium_service),
) -> SanatoriumAdminRead:
    sanatorium = await sanatoriums.get_by_id(sanatorium_id)
    if sanatorium is None:
        raise not_found("Sanatorium not found")
    _ensure_can_edit(sanatorium, current_user)
    updated = await sanatoriums.update(sanatorium, payload, actor=current_user)
    return SanatoriumAdminRead.model_validate(updated)


@router.post(
    "/{sanatorium_id}/approve",
    response_model=SanatoriumAdminRead,
    dependencies=[Depends(require_super_admin)],
)
async def approve_sanatorium(
    sanatorium_id: uuid.UUID,
    sanatoriums: SanatoriumService = Depends(get_sanatorium_service),
) -> SanatoriumAdminRead:
    sanatorium = await sanatoriums.get_by_id(sanatorium_id)
    if sanatorium is None:
        raise not_found("Sanatorium not found")
    approved = await sanatoriums.approve(sanatorium)
    return SanatoriumAdminRead.model_validate(approved)


@router.post(
    "/{sanatorium_id}/reject",
    response_model=SanatoriumAdminRead,
    dependencies=[Depends(require_super_admin)],
)
async def reject_sanatorium(
    sanatorium_id: uuid.UUID,
    sanatoriums: SanatoriumService = Depends(get_sanatorium_service),
) -> SanatoriumAdminRead:
    sanatorium = await sanatoriums.get_by_id(sanatorium_id)
    if sanatorium is None:
        raise not_found("Sanatorium not found")
    rejected = await sanatoriums.reject(sanatorium)
    return SanatoriumAdminRead.model_validate(rejected)


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
    _ensure_can_edit(sanatorium, current_user)

    content, mime = await read_upload(
        file, detect_mime=detect_image_mime, allowed_label="JPEG, PNG, WebP"
    )

    image = await images.add(
        sanatorium=sanatorium,
        content=content,
        content_type=mime,
        storage=storage,
        caption=caption,
        is_primary=is_primary,
        is_360=is_360,
        category=category,
        caption_i18n=_json_form(caption_i18n, default={}),
        alt_text=_json_form(alt_text, default={}),
        tags=_json_form(tags, default=[]),
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
    _ensure_can_edit(sanatorium, current_user)
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
    _ensure_can_edit(sanatorium, current_user)
    await images.delete(image, storage)
