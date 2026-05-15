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
from app.services.program_service import ProgramService, get_program_service

router = APIRouter(prefix="/programs", tags=["programs"])

require_admin_or_above = require_roles(UserRole.ADMIN, UserRole.SUPER_ADMIN)


@router.get("", response_model=TreatmentProgramList)
async def list_programs(
    sanatorium_id: uuid.UUID = Query(...),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    programs: ProgramService = Depends(get_program_service),
) -> TreatmentProgramList:
    items, total = await programs.list_for_sanatorium(
        sanatorium_id, limit=limit, offset=offset
    )
    return TreatmentProgramList(
        items=list(items), total=total, limit=limit, offset=offset
    )


@router.get("/{program_id}", response_model=TreatmentProgramRead)
async def get_program(
    program_id: uuid.UUID,
    programs: ProgramService = Depends(get_program_service),
) -> TreatmentProgramRead:
    program = await programs.get_by_id(program_id)
    if program is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Program not found"
        )
    return TreatmentProgramRead.model_validate(program)


@router.post(
    "",
    response_model=TreatmentProgramRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin_or_above)],
)
async def create_program(
    payload: TreatmentProgramCreate,
    current_user: CurrentUser,
    programs: ProgramService = Depends(get_program_service),
) -> TreatmentProgramRead:
    program = await programs.create(payload, current_user)
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
    programs: ProgramService = Depends(get_program_service),
) -> TreatmentProgramRead:
    program = await programs.get_by_id(program_id)
    if program is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Program not found"
        )
    updated = await programs.update(program, payload, current_user)
    return TreatmentProgramRead.model_validate(updated)


@router.delete(
    "/{program_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin_or_above)],
)
async def delete_program(
    program_id: uuid.UUID,
    current_user: CurrentUser,
    programs: ProgramService = Depends(get_program_service),
) -> None:
    program = await programs.get_by_id(program_id)
    if program is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Program not found"
        )
    await programs.delete(program, current_user)
