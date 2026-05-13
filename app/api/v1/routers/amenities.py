import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import CurrentUser, require_roles
from app.models.user import UserRole
from app.schemas.amenity import AmenityCreate, AmenityList, AmenityRead, AmenityUpdate
from app.services.amenity_service import AmenityService, get_amenity_service

router = APIRouter(prefix="/amenities", tags=["amenities"])

require_super_admin = require_roles(UserRole.SUPER_ADMIN)


@router.get("", response_model=AmenityList)
async def list_amenities(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    svc: AmenityService = Depends(get_amenity_service),
) -> AmenityList:
    items, total = await svc.list_amenities(limit=limit, offset=offset)
    return AmenityList(items=list(items), total=total, limit=limit, offset=offset)


@router.post(
    "",
    response_model=AmenityRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_super_admin)],
)
async def create_amenity(
    payload: AmenityCreate,
    svc: AmenityService = Depends(get_amenity_service),
) -> AmenityRead:
    return AmenityRead.model_validate(await svc.create_amenity(payload))


@router.get("/{amenity_id}", response_model=AmenityRead)
async def get_amenity(
    amenity_id: uuid.UUID,
    svc: AmenityService = Depends(get_amenity_service),
) -> AmenityRead:
    amenity = await svc.get_amenity(amenity_id)
    if amenity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Amenity not found")
    return AmenityRead.model_validate(amenity)


@router.patch(
    "/{amenity_id}",
    response_model=AmenityRead,
    dependencies=[Depends(require_super_admin)],
)
async def update_amenity(
    amenity_id: uuid.UUID,
    payload: AmenityUpdate,
    svc: AmenityService = Depends(get_amenity_service),
) -> AmenityRead:
    amenity = await svc.get_amenity(amenity_id)
    if amenity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Amenity not found")
    return AmenityRead.model_validate(await svc.update_amenity(amenity, payload))


@router.delete(
    "/{amenity_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_super_admin)],
)
async def delete_amenity(
    amenity_id: uuid.UUID,
    svc: AmenityService = Depends(get_amenity_service),
) -> None:
    amenity = await svc.get_amenity(amenity_id)
    if amenity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Amenity not found")
    await svc.delete_amenity(amenity)
