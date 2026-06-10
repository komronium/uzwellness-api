import uuid
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Path,
    Query,
    UploadFile,
    status,
)

from app.api.deps import (
    IncludeTranslationsDep,
    is_super_admin,
    LocaleDep,
    not_found,
    OptionalUser,
    require_roles,
)
from app.core.pagination import LargePagination
from app.core.storage import StorageBackend, get_storage
from app.core.uploads import read_image_upload_as_webp
from app.models.user import UserRole
from app.schemas.treatment_focus import (
    TreatmentFocusAdminList,
    TreatmentFocusAdminRead,
    TreatmentFocusCreate,
    TreatmentFocusList,
    TreatmentFocusRead,
    TreatmentFocusTileList,
    TreatmentFocusTileRead,
    TreatmentFocusUpdate,
)
from app.services.treatment_focus_service import (
    TreatmentFocusService,
    get_treatment_focus_service,
)

router = APIRouter(prefix="/treatment-focuses", tags=["Treatments"])

require_super_admin = require_roles(UserRole.SUPER_ADMIN)


@router.get("", response_model=TreatmentFocusList | TreatmentFocusAdminList)
async def list_treatment_focuses(
    current_user: OptionalUser,
    locale: LocaleDep,
    include_translations: IncludeTranslationsDep,
    page: LargePagination,
    focuses: TreatmentFocusService = Depends(get_treatment_focus_service),
    active_only: bool = Query(default=True),
) -> TreatmentFocusList | TreatmentFocusAdminList:
    super_admin = is_super_admin(current_user)
    items, total = await focuses.list_all(
        limit=page.limit,
        offset=page.offset,
        active_only=active_only or not super_admin,
    )
    if include_translations and super_admin:
        return TreatmentFocusAdminList(
            items=[TreatmentFocusAdminRead.model_validate(item) for item in items],
            total=total,
            limit=page.limit,
            offset=page.offset,
        )
    return TreatmentFocusList(
        items=[TreatmentFocusRead.from_obj(item, locale) for item in items],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/tiles", response_model=TreatmentFocusTileList)
async def list_treatment_focus_tiles(
    locale: LocaleDep,
    focuses: TreatmentFocusService = Depends(get_treatment_focus_service),
) -> TreatmentFocusTileList:
    rows = await focuses.list_tiles()
    return TreatmentFocusTileList(
        items=[
            TreatmentFocusTileRead(
                **TreatmentFocusRead.from_obj(focus, locale).model_dump(),
                programs_count=programs_count,
                sanatoriums_count=sanatoriums_count,
            )
            for focus, programs_count, sanatoriums_count in rows
        ],
        total=len(rows),
    )


@router.get(
    "/{slug_or_id}", response_model=TreatmentFocusRead | TreatmentFocusAdminRead
)
async def get_treatment_focus(
    slug_or_id: Annotated[str, Path(min_length=1, max_length=120)],
    current_user: OptionalUser,
    locale: LocaleDep,
    include_translations: IncludeTranslationsDep,
    focuses: TreatmentFocusService = Depends(get_treatment_focus_service),
) -> TreatmentFocusRead | TreatmentFocusAdminRead:
    focus = None
    try:
        focus = await focuses.get_by_id(uuid.UUID(slug_or_id))
    except ValueError:
        focus = await focuses.get_by_slug(slug_or_id)
    if focus is None:
        raise not_found("Treatment focus not found")

    super_admin = is_super_admin(current_user)
    if not focus.is_active and not super_admin:
        raise not_found("Treatment focus not found")
    if include_translations and super_admin:
        return TreatmentFocusAdminRead.model_validate(focus)
    return TreatmentFocusRead.from_obj(focus, locale)


@router.post(
    "",
    response_model=TreatmentFocusAdminRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_super_admin)],
)
async def create_treatment_focus(
    payload: TreatmentFocusCreate,
    focuses: TreatmentFocusService = Depends(get_treatment_focus_service),
) -> TreatmentFocusAdminRead:
    focus = await focuses.create(payload)
    return TreatmentFocusAdminRead.model_validate(focus)


@router.patch(
    "/{focus_id}",
    response_model=TreatmentFocusAdminRead,
    dependencies=[Depends(require_super_admin)],
)
async def update_treatment_focus(
    focus_id: uuid.UUID,
    payload: TreatmentFocusUpdate,
    focuses: TreatmentFocusService = Depends(get_treatment_focus_service),
) -> TreatmentFocusAdminRead:
    focus = await focuses.get_by_id(focus_id)
    if focus is None:
        raise not_found("Treatment focus not found")
    updated = await focuses.update(focus, payload)
    return TreatmentFocusAdminRead.model_validate(updated)


@router.post(
    "/{focus_id}/image",
    response_model=TreatmentFocusAdminRead,
    dependencies=[Depends(require_super_admin)],
)
async def upload_treatment_focus_image(
    focus_id: uuid.UUID,
    file: Annotated[UploadFile, File(...)],
    focuses: TreatmentFocusService = Depends(get_treatment_focus_service),
    storage: StorageBackend = Depends(get_storage),
) -> TreatmentFocusAdminRead:
    focus = await focuses.get_by_id(focus_id)
    if focus is None:
        raise not_found("Treatment focus not found")
    try:
        content, content_type = await read_image_upload_as_webp(file)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=str(exc),
        ) from exc
    updated = await focuses.update_image(
        focus,
        content=content,
        content_type=content_type,
        storage=storage,
    )
    return TreatmentFocusAdminRead.model_validate(updated)


@router.delete(
    "/{focus_id}/image",
    response_model=TreatmentFocusAdminRead,
    dependencies=[Depends(require_super_admin)],
)
async def delete_treatment_focus_image(
    focus_id: uuid.UUID,
    focuses: TreatmentFocusService = Depends(get_treatment_focus_service),
    storage: StorageBackend = Depends(get_storage),
) -> TreatmentFocusAdminRead:
    focus = await focuses.get_by_id(focus_id)
    if focus is None:
        raise not_found("Treatment focus not found")
    updated = await focuses.delete_image(focus, storage)
    return TreatmentFocusAdminRead.model_validate(updated)


@router.delete(
    "/{focus_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_super_admin)],
)
async def delete_treatment_focus(
    focus_id: uuid.UUID,
    focuses: TreatmentFocusService = Depends(get_treatment_focus_service),
) -> None:
    focus = await focuses.get_by_id(focus_id)
    if focus is None:
        raise not_found("Treatment focus not found")
    await focuses.delete(focus)
