import uuid

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import (
    CurrentUser,
    IncludeTranslationsDep,
    LocaleDep,
    not_found,
    require_roles,
)
from app.core.pagination import Pagination
from app.models.user import UserRole
from app.schemas.rate_plan import (
    RatePlanAdminList,
    RatePlanAdminRead,
    RatePlanCreate,
    RatePlanList,
    RatePlanRead,
    RatePlanUpdate,
)
from app.services.rate_plan_service import RatePlanService, get_rate_plan_service

router = APIRouter(prefix="/rate-plans", tags=["rate-plans"])

require_admin_or_above = require_roles(UserRole.ADMIN, UserRole.SUPER_ADMIN)


@router.get("", response_model=None)
async def list_rate_plans(
    locale: LocaleDep,
    include_translations: IncludeTranslationsDep,
    page: Pagination,
    room_id: uuid.UUID = Query(...),
    rate_plans: RatePlanService = Depends(get_rate_plan_service),
) -> RatePlanList | RatePlanAdminList:
    items, total = await rate_plans.list_for_room(
        room_id, limit=page.limit, offset=page.offset
    )
    if include_translations:
        return RatePlanAdminList(
            items=[RatePlanAdminRead.model_validate(rp) for rp in items],
            total=total,
            limit=page.limit,
            offset=page.offset,
        )
    return RatePlanList(
        items=[RatePlanRead.from_obj(rp, locale) for rp in items],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/{rate_plan_id}", response_model=None)
async def get_rate_plan(
    rate_plan_id: uuid.UUID,
    locale: LocaleDep,
    include_translations: IncludeTranslationsDep,
    rate_plans: RatePlanService = Depends(get_rate_plan_service),
) -> RatePlanRead | RatePlanAdminRead:
    rate_plan = await rate_plans.get_by_id(rate_plan_id)
    if rate_plan is None:
        raise not_found("Rate plan not found")
    if include_translations:
        return RatePlanAdminRead.model_validate(rate_plan)
    return RatePlanRead.from_obj(rate_plan, locale)


@router.post(
    "",
    response_model=RatePlanAdminRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin_or_above)],
)
async def create_rate_plan(
    payload: RatePlanCreate,
    current_user: CurrentUser,
    rate_plans: RatePlanService = Depends(get_rate_plan_service),
) -> RatePlanAdminRead:
    rate_plan = await rate_plans.create(payload, current_user)
    return RatePlanAdminRead.model_validate(rate_plan)


@router.patch(
    "/{rate_plan_id}",
    response_model=RatePlanAdminRead,
    dependencies=[Depends(require_admin_or_above)],
)
async def update_rate_plan(
    rate_plan_id: uuid.UUID,
    payload: RatePlanUpdate,
    current_user: CurrentUser,
    rate_plans: RatePlanService = Depends(get_rate_plan_service),
) -> RatePlanAdminRead:
    rate_plan = await rate_plans.get_by_id(rate_plan_id)
    if rate_plan is None:
        raise not_found("Rate plan not found")
    updated = await rate_plans.update(rate_plan, payload, current_user)
    return RatePlanAdminRead.model_validate(updated)


@router.delete(
    "/{rate_plan_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin_or_above)],
)
async def delete_rate_plan(
    rate_plan_id: uuid.UUID,
    current_user: CurrentUser,
    rate_plans: RatePlanService = Depends(get_rate_plan_service),
) -> None:
    rate_plan = await rate_plans.get_by_id(rate_plan_id)
    if rate_plan is None:
        raise not_found("Rate plan not found")
    await rate_plans.delete(rate_plan, current_user)
