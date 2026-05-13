import uuid
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

from app.api.deps import CurrentUser, OptionalUser, require_roles
from app.core.config import settings
from app.models.sanatorium import SanatoriumStatus
from app.models.user import User, UserRole
from app.schemas.sanatorium import (
    SanatoriumCreate,
    SanatoriumImageRead,
    SanatoriumList,
    SanatoriumRead,
    SanatoriumUpdate,
)
from app.services.sanatorium_service import (
    SanatoriumService,
    get_sanatorium_service,
)
from app.services.storage import StorageBackend, detect_image_mime, get_storage

router = APIRouter(prefix="/sanatoriums", tags=["sanatoriums"])

require_super_admin = require_roles(UserRole.SUPER_ADMIN)


def _ensure_can_edit(sanatorium_owner_id: uuid.UUID | None, user: User) -> None:
    if user.role == UserRole.SUPER_ADMIN:
        return
    if user.role == UserRole.ADMIN and sanatorium_owner_id == user.id:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Not allowed to modify this sanatorium",
    )


SortField = Literal[
    "name", "-name", "stars", "-stars", "rating", "-rating", "created_at", "-created_at"
]


@router.get("", response_model=SanatoriumList)
async def list_sanatoriums(
    current_user: OptionalUser,
    sanatoriums: SanatoriumService = Depends(get_sanatorium_service),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    city: str | None = Query(default=None, max_length=120),
    status_filter: SanatoriumStatus | None = Query(default=None, alias="status"),
    stars: int | None = Query(default=None, ge=1, le=5),
    q: str | None = Query(default=None, max_length=200),
    sort: SortField = Query(default="-created_at"),
    amenity_ids: Annotated[list[uuid.UUID] | None, Query()] = None,
    treatment_focus: str | None = Query(default=None, max_length=60),
) -> SanatoriumList:
    items, total = await sanatoriums.list_for_user(
        user=current_user,
        limit=limit,
        offset=offset,
        city=city,
        status_filter=status_filter,
        stars=stars,
        q=q,
        sort=sort,
        amenity_ids=amenity_ids,
        treatment_focus=treatment_focus,
    )
    return SanatoriumList(
        items=[SanatoriumRead.model_validate(s) for s in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{sanatorium_id}", response_model=SanatoriumRead)
async def get_sanatorium(
    sanatorium_id: uuid.UUID,
    current_user: OptionalUser,
    sanatoriums: SanatoriumService = Depends(get_sanatorium_service),
) -> SanatoriumRead:
    sanatorium = await sanatoriums.get_visible(sanatorium_id, current_user)
    if sanatorium is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sanatorium not found",
        )
    return SanatoriumRead.model_validate(sanatorium)


@router.post(
    "",
    response_model=SanatoriumRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_super_admin)],
)
async def create_sanatorium(
    payload: SanatoriumCreate,
    sanatoriums: SanatoriumService = Depends(get_sanatorium_service),
) -> SanatoriumRead:
    sanatorium = await sanatoriums.create(payload)
    return SanatoriumRead.model_validate(sanatorium)


@router.patch("/{sanatorium_id}", response_model=SanatoriumRead)
async def update_sanatorium(
    sanatorium_id: uuid.UUID,
    payload: SanatoriumUpdate,
    current_user: CurrentUser,
    sanatoriums: SanatoriumService = Depends(get_sanatorium_service),
) -> SanatoriumRead:
    sanatorium = await sanatoriums.get_by_id(sanatorium_id)
    if sanatorium is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sanatorium not found",
        )
    _ensure_can_edit(sanatorium.admin_user_id, current_user)
    updated = await sanatoriums.update(sanatorium, payload)
    return SanatoriumRead.model_validate(updated)


@router.post(
    "/{sanatorium_id}/approve",
    response_model=SanatoriumRead,
    dependencies=[Depends(require_super_admin)],
)
async def approve_sanatorium(
    sanatorium_id: uuid.UUID,
    sanatoriums: SanatoriumService = Depends(get_sanatorium_service),
) -> SanatoriumRead:
    sanatorium = await sanatoriums.get_by_id(sanatorium_id)
    if sanatorium is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sanatorium not found",
        )
    approved = await sanatoriums.approve(sanatorium)
    return SanatoriumRead.model_validate(approved)


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
    order: int = Form(default=0, ge=0),
    sanatoriums: SanatoriumService = Depends(get_sanatorium_service),
    storage: StorageBackend = Depends(get_storage),
) -> SanatoriumImageRead:
    sanatorium = await sanatoriums.get_by_id(sanatorium_id)
    if sanatorium is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sanatorium not found",
        )
    _ensure_can_edit(sanatorium.admin_user_id, current_user)

    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File exceeds {settings.MAX_UPLOAD_SIZE_MB} MB limit",
        )
    if len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file",
        )

    mime = detect_image_mime(content)
    if mime is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported file type (allowed: JPEG, PNG, WebP)",
        )

    image = await sanatoriums.add_image(
        sanatorium=sanatorium,
        content=content,
        content_type=mime,
        storage=storage,
        caption=caption,
        is_primary=is_primary,
        order=order,
    )
    return SanatoriumImageRead.model_validate(image)
