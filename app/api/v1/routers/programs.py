import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import CurrentUser, require_roles
from app.models.user import UserRole
from app.schemas.amenity import (
    TreatmentProgramCreate,
    TreatmentProgramList,
    TreatmentProgramRead,
    TreatmentProgramUpdate,
)
from app.services.amenity_service import AmenityService, get_amenity_service

router = APIRouter(prefix="/programs", tags=["programs"])

require_admin_or_above = require_roles(UserRole.ADMIN, UserRole.SUPER_ADMIN)


@router.get("", response_model=TreatmentProgramList)
async def list_programs(
    sanatorium_id: uuid.UUID = Query(...),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    svc: AmenityService = Depends(get_amenity_service),
) -> TreatmentProgramList:
    items, total = await svc.list_programs(sanatorium_id, limit=limit, offset=offset)
    return TreatmentProgramList(items=list(items), total=total, limit=limit, offset=offset)


@router.post(
    "",
    response_model=TreatmentProgramRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin_or_above)],
)
async def create_program(
    payload: TreatmentProgramCreate,
    current_user: CurrentUser,
    svc: AmenityService = Depends(get_amenity_service),
) -> TreatmentProgramRead:
    program = await svc.create_program(payload, current_user)
    return TreatmentProgramRead.model_validate(program)


@router.get("/{program_id}", response_model=TreatmentProgramRead)
async def get_program(
    program_id: uuid.UUID,
    svc: AmenityService = Depends(get_amenity_service),
) -> TreatmentProgramRead:
    program = await svc._load_program(program_id)
    if program is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Program not found")
    return TreatmentProgramRead.model_validate(program)


@router.patch(
    "/{program_id}",
    response_model=TreatmentProgramRead,
    dependencies=[Depends(require_admin_or_above)],
)
async def update_program(
    program_id: uuid.UUID,
    payload: TreatmentProgramUpdate,
    current_user: CurrentUser,
    svc: AmenityService = Depends(get_amenity_service),
) -> TreatmentProgramRead:
    program = await svc._load_program(program_id)
    if program is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Program not found")
    updated = await svc.update_program(program, payload, current_user)
    return TreatmentProgramRead.model_validate(updated)


@router.delete(
    "/{program_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin_or_above)],
)
async def delete_program(
    program_id: uuid.UUID,
    current_user: CurrentUser,
    svc: AmenityService = Depends(get_amenity_service),
) -> None:
    program = await svc._load_program(program_id)
    if program is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Program not found")
    await svc._check_sanatorium_access(program.sanatorium_id, current_user)
    await svc.delete_program(program)
