import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import IncludeTranslationsDep, LocaleDep, require_roles
from app.models.user import UserRole
from app.schemas.amenity import (
    AmenityAdminList,
    AmenityAdminRead,
    AmenityCreate,
    AmenityList,
    AmenityRead,
    AmenityUpdate,
)
from app.services.amenity_service import AmenityService, get_amenity_service

router = APIRouter(prefix="/amenities", tags=["amenities"])

require_super_admin = require_roles(UserRole.SUPER_ADMIN)


@router.get("", response_model=None)
async def list_amenities(
    locale: LocaleDep,
    include_translations: IncludeTranslationsDep,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    amenities: AmenityService = Depends(get_amenity_service),
) -> AmenityList | AmenityAdminList:
    items, total = await amenities.list_all(limit=limit, offset=offset)
    if include_translations:
        return AmenityAdminList(
            items=[AmenityAdminRead.model_validate(a) for a in items],
            total=total,
            limit=limit,
            offset=offset,
        )
    return AmenityList(
        items=[AmenityRead.from_obj(a, locale) for a in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{amenity_id}", response_model=None)
async def get_amenity(
    amenity_id: uuid.UUID,
    locale: LocaleDep,
    include_translations: IncludeTranslationsDep,
    amenities: AmenityService = Depends(get_amenity_service),
) -> AmenityRead | AmenityAdminRead:
    amenity = await amenities.get_by_id(amenity_id)
    if amenity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Amenity not found"
        )
    if include_translations:
        return AmenityAdminRead.model_validate(amenity)
    return AmenityRead.from_obj(amenity, locale)


@router.post(
    "",
    response_model=AmenityAdminRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_super_admin)],
)
async def create_amenity(
    payload: AmenityCreate,
    amenities: AmenityService = Depends(get_amenity_service),
) -> AmenityAdminRead:
    return AmenityAdminRead.model_validate(await amenities.create(payload))


@router.patch(
    "/{amenity_id}",
    response_model=AmenityAdminRead,
    dependencies=[Depends(require_super_admin)],
)
async def update_amenity(
    amenity_id: uuid.UUID,
    payload: AmenityUpdate,
    amenities: AmenityService = Depends(get_amenity_service),
) -> AmenityAdminRead:
    amenity = await amenities.get_by_id(amenity_id)
    if amenity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Amenity not found"
        )
    return AmenityAdminRead.model_validate(await amenities.update(amenity, payload))


@router.delete(
    "/{amenity_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_super_admin)],
)
async def delete_amenity(
    amenity_id: uuid.UUID,
    amenities: AmenityService = Depends(get_amenity_service),
) -> None:
    amenity = await amenities.get_by_id(amenity_id)
    if amenity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Amenity not found"
        )
    await amenities.delete(amenity)
