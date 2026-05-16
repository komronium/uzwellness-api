import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import CurrentUser, require_roles
from app.models.user import UserRole
from app.schemas.extra_bed import (
    ExtraBedConfigCreate,
    ExtraBedConfigList,
    ExtraBedConfigRead,
    ExtraBedConfigUpdate,
)
from app.services.extra_bed_service import ExtraBedService, get_extra_bed_service

router = APIRouter(prefix="/extra-beds", tags=["extra-beds"])

require_admin_or_above = require_roles(UserRole.ADMIN, UserRole.SUPER_ADMIN)


@router.get("", response_model=ExtraBedConfigList)
async def list_extra_beds(
    sanatorium_id: uuid.UUID = Query(...),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    extra_beds: ExtraBedService = Depends(get_extra_bed_service),
) -> ExtraBedConfigList:
    items, total = await extra_beds.list_for_sanatorium(
        sanatorium_id, limit=limit, offset=offset
    )
    return ExtraBedConfigList(
        items=[ExtraBedConfigRead.model_validate(c) for c in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{config_id}", response_model=ExtraBedConfigRead)
async def get_extra_bed(
    config_id: uuid.UUID,
    extra_beds: ExtraBedService = Depends(get_extra_bed_service),
) -> ExtraBedConfigRead:
    config = await extra_beds.get_by_id(config_id)
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Extra bed config not found",
        )
    return ExtraBedConfigRead.model_validate(config)


@router.post(
    "",
    response_model=ExtraBedConfigRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin_or_above)],
)
async def create_extra_bed(
    payload: ExtraBedConfigCreate,
    current_user: CurrentUser,
    extra_beds: ExtraBedService = Depends(get_extra_bed_service),
) -> ExtraBedConfigRead:
    config = await extra_beds.create(payload, current_user)
    return ExtraBedConfigRead.model_validate(config)


@router.patch(
    "/{config_id}",
    response_model=ExtraBedConfigRead,
    dependencies=[Depends(require_admin_or_above)],
)
async def update_extra_bed(
    config_id: uuid.UUID,
    payload: ExtraBedConfigUpdate,
    current_user: CurrentUser,
    extra_beds: ExtraBedService = Depends(get_extra_bed_service),
) -> ExtraBedConfigRead:
    config = await extra_beds.get_by_id(config_id)
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Extra bed config not found",
        )
    updated = await extra_beds.update(config, payload, current_user)
    return ExtraBedConfigRead.model_validate(updated)


@router.delete(
    "/{config_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin_or_above)],
)
async def delete_extra_bed(
    config_id: uuid.UUID,
    current_user: CurrentUser,
    extra_beds: ExtraBedService = Depends(get_extra_bed_service),
) -> None:
    config = await extra_beds.get_by_id(config_id)
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Extra bed config not found",
        )
    await extra_beds.delete(config, current_user)
