import uuid

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import (
    IncludeTranslationsDep,
    LocaleDep,
    not_found,
    require_roles,
)
from app.core.pagination import LargePagination
from app.models.transfer_location import TransferLocationKind
from app.models.user import UserRole
from app.schemas.transfer_location import (
    TransferLocationAdminList,
    TransferLocationAdminRead,
    TransferLocationCreate,
    TransferLocationList,
    TransferLocationRead,
    TransferLocationUpdate,
)
from app.services.transfer_location_service import (
    TransferLocationService,
    get_transfer_location_service,
)

router = APIRouter(prefix="/transfer-locations", tags=["Travel Services"])

require_transfer_admin = require_roles(UserRole.TRANSFER_ADMIN, UserRole.SUPER_ADMIN)


@router.get("", response_model=TransferLocationList | TransferLocationAdminList)
async def list_transfer_locations(
    locale: LocaleDep,
    include_translations: IncludeTranslationsDep,
    page: LargePagination,
    is_active: bool | None = Query(default=None),
    kind: TransferLocationKind | None = Query(default=None),
    locations: TransferLocationService = Depends(get_transfer_location_service),
) -> TransferLocationList | TransferLocationAdminList:
    items, total = await locations.list_all(
        limit=page.limit,
        offset=page.offset,
        is_active=is_active,
        kind=kind,
    )
    if include_translations:
        return TransferLocationAdminList(
            items=[TransferLocationAdminRead.model_validate(i) for i in items],
            total=total,
            limit=page.limit,
            offset=page.offset,
        )
    return TransferLocationList(
        items=[TransferLocationRead.from_obj(i, locale) for i in items],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get(
    "/{location_id}", response_model=TransferLocationRead | TransferLocationAdminRead
)
async def get_transfer_location(
    location_id: uuid.UUID,
    locale: LocaleDep,
    include_translations: IncludeTranslationsDep,
    locations: TransferLocationService = Depends(get_transfer_location_service),
) -> TransferLocationRead | TransferLocationAdminRead:
    location = await locations.get_by_id(location_id)
    if location is None:
        raise not_found("Transfer location not found")
    if include_translations:
        return TransferLocationAdminRead.model_validate(location)
    return TransferLocationRead.from_obj(location, locale)


@router.post(
    "",
    response_model=TransferLocationAdminRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_transfer_admin)],
)
async def create_transfer_location(
    payload: TransferLocationCreate,
    locations: TransferLocationService = Depends(get_transfer_location_service),
) -> TransferLocationAdminRead:
    return TransferLocationAdminRead.model_validate(await locations.create(payload))


@router.patch(
    "/{location_id}",
    response_model=TransferLocationAdminRead,
    dependencies=[Depends(require_transfer_admin)],
)
async def update_transfer_location(
    location_id: uuid.UUID,
    payload: TransferLocationUpdate,
    locations: TransferLocationService = Depends(get_transfer_location_service),
) -> TransferLocationAdminRead:
    location = await locations.get_by_id(location_id)
    if location is None:
        raise not_found("Transfer location not found")
    return TransferLocationAdminRead.model_validate(
        await locations.update(location, payload)
    )


@router.delete(
    "/{location_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_transfer_admin)],
)
async def delete_transfer_location(
    location_id: uuid.UUID,
    locations: TransferLocationService = Depends(get_transfer_location_service),
) -> None:
    location = await locations.get_by_id(location_id)
    if location is None:
        raise not_found("Transfer location not found")
    await locations.delete(location)
