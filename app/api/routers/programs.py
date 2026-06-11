import uuid

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import (
    ConverterDep,
    CurrentUser,
    IncludeTranslationsDep,
    LocaleDep,
    not_found,
    require_roles,
)
from app.core.pagination import Pagination
from app.models.user import UserRole
from app.schemas.program import (
    TreatmentProgramAdminList,
    TreatmentProgramAdminRead,
    TreatmentProgramCreate,
    TreatmentProgramList,
    TreatmentProgramRead,
    TreatmentProgramUpdate,
)
from app.services.program_service import ProgramService, get_program_service

router = APIRouter(prefix="/programs", tags=["Treatments"])

require_admin_or_above = require_roles(UserRole.ADMIN, UserRole.SUPER_ADMIN)


@router.get("", response_model=TreatmentProgramList | TreatmentProgramAdminList)
async def list_programs(
    locale: LocaleDep,
    converter: ConverterDep,
    include_translations: IncludeTranslationsDep,
    page: Pagination,
    sanatorium_id: uuid.UUID = Query(...),
    programs: ProgramService = Depends(get_program_service),
) -> TreatmentProgramList | TreatmentProgramAdminList:
    items, total = await programs.list_for_sanatorium(
        sanatorium_id, limit=page.limit, offset=page.offset
    )
    if include_translations:
        return TreatmentProgramAdminList(
            items=[TreatmentProgramAdminRead.model_validate(p) for p in items],
            total=total,
            limit=page.limit,
            offset=page.offset,
        )
    return TreatmentProgramList(
        items=[TreatmentProgramRead.from_obj(p, locale, converter) for p in items],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get(
    "/{program_id}", response_model=TreatmentProgramRead | TreatmentProgramAdminRead
)
async def get_program(
    program_id: uuid.UUID,
    locale: LocaleDep,
    converter: ConverterDep,
    include_translations: IncludeTranslationsDep,
    programs: ProgramService = Depends(get_program_service),
) -> TreatmentProgramRead | TreatmentProgramAdminRead:
    program = await programs.get_by_id(program_id)
    if program is None:
        raise not_found("Program not found")
    if include_translations:
        return TreatmentProgramAdminRead.model_validate(program)
    return TreatmentProgramRead.from_obj(program, locale, converter)


@router.post(
    "",
    response_model=TreatmentProgramAdminRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin_or_above)],
)
async def create_program(
    payload: TreatmentProgramCreate,
    current_user: CurrentUser,
    programs: ProgramService = Depends(get_program_service),
) -> TreatmentProgramAdminRead:
    program = await programs.create(payload, current_user)
    return TreatmentProgramAdminRead.model_validate(program)


@router.patch(
    "/{program_id}",
    response_model=TreatmentProgramAdminRead,
    dependencies=[Depends(require_admin_or_above)],
)
async def update_program(
    program_id: uuid.UUID,
    payload: TreatmentProgramUpdate,
    current_user: CurrentUser,
    programs: ProgramService = Depends(get_program_service),
) -> TreatmentProgramAdminRead:
    program = await programs.get_by_id(program_id)
    if program is None:
        raise not_found("Program not found")
    updated = await programs.update(program, payload, current_user)
    return TreatmentProgramAdminRead.model_validate(updated)


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
        raise not_found("Program not found")
    await programs.delete(program, current_user)
