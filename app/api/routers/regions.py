import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import IncludeTranslationsDep, LocaleDep, require_roles
from app.models.user import UserRole
from app.schemas.region import (
    RegionAdminList,
    RegionAdminRead,
    RegionCreate,
    RegionList,
    RegionRead,
    RegionUpdate,
)
from app.services.region_service import RegionService, get_region_service

router = APIRouter(prefix="/regions", tags=["regions"])

require_super_admin = require_roles(UserRole.SUPER_ADMIN)


@router.get("", response_model=None)
async def list_regions(
    locale: LocaleDep,
    include_translations: IncludeTranslationsDep,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    active_only: bool = Query(default=False),
    regions: RegionService = Depends(get_region_service),
) -> RegionList | RegionAdminList:
    items, total = await regions.list_all(
        limit=limit, offset=offset, active_only=active_only
    )
    if include_translations:
        return RegionAdminList(
            items=[RegionAdminRead.model_validate(r) for r in items],
            total=total,
            limit=limit,
            offset=offset,
        )
    return RegionList(
        items=[RegionRead.from_obj(r, locale) for r in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{slug_or_id}", response_model=None)
async def get_region(
    slug_or_id: str,
    locale: LocaleDep,
    include_translations: IncludeTranslationsDep,
    regions: RegionService = Depends(get_region_service),
) -> RegionRead | RegionAdminRead:
    region = None
    try:
        region_uuid = uuid.UUID(slug_or_id)
    except ValueError:
        region = await regions.get_by_slug(slug_or_id)
    else:
        region = await regions.get_by_id(region_uuid)
    if region is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Region not found"
        )
    if include_translations:
        return RegionAdminRead.model_validate(region)
    return RegionRead.from_obj(region, locale)


@router.post(
    "",
    response_model=RegionAdminRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_super_admin)],
)
async def create_region(
    payload: RegionCreate,
    regions: RegionService = Depends(get_region_service),
) -> RegionAdminRead:
    return RegionAdminRead.model_validate(await regions.create(payload))


@router.patch(
    "/{region_id}",
    response_model=RegionAdminRead,
    dependencies=[Depends(require_super_admin)],
)
async def update_region(
    region_id: uuid.UUID,
    payload: RegionUpdate,
    regions: RegionService = Depends(get_region_service),
) -> RegionAdminRead:
    region = await regions.get_by_id(region_id)
    if region is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Region not found"
        )
    return RegionAdminRead.model_validate(await regions.update(region, payload))


@router.delete(
    "/{region_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_super_admin)],
)
async def delete_region(
    region_id: uuid.UUID,
    regions: RegionService = Depends(get_region_service),
) -> None:
    region = await regions.get_by_id(region_id)
    if region is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Region not found"
        )
    await regions.delete(region)
