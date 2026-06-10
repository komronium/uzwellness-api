import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import (
    CurrentUser,
    IncludeTranslationsDep,
    is_admin_or_above,
    LocaleDep,
    not_found,
    OptionalUser,
    require_roles,
)
from app.core.pagination import Pagination
from app.models.user import UserRole
from app.schemas.rate_plan import (
    RatePlanAdminDirectoryItem,
    RatePlanAdminDirectoryList,
    RatePlanAdminList,
    RatePlanAdminRead,
    RatePlanCreate,
    RatePlanList,
    RatePlanRead,
    RatePlanUpdate,
)
from app.services.rate_plan_service import RatePlanService, get_rate_plan_service

router = APIRouter(prefix="/rate-plans", tags=["Rooms"])

require_admin_or_above = require_roles(UserRole.ADMIN, UserRole.SUPER_ADMIN)


@router.get(
    "", response_model=RatePlanList | RatePlanAdminList | RatePlanAdminDirectoryList
)
async def list_rate_plans(
    locale: LocaleDep,
    include_translations: IncludeTranslationsDep,
    page: Pagination,
    current_user: OptionalUser,
    room_id: uuid.UUID | None = Query(default=None),
    sanatorium_id: uuid.UUID | None = Query(default=None),
    rate_plan_ids: list[uuid.UUID] | None = Query(default=None),
    hide_inactive: bool = Query(default=False),
    rate_plans: RatePlanService = Depends(get_rate_plan_service),
) -> RatePlanList | RatePlanAdminList | RatePlanAdminDirectoryList:
    if sanatorium_id is not None:
        if not is_admin_or_above(current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        items, total = await rate_plans.list_for_sanatorium(
            sanatorium_id,
            current_user,
            room_id=room_id,
            rate_plan_ids=rate_plan_ids,
            hide_inactive=hide_inactive,
            limit=page.limit,
            offset=page.offset,
        )
        return RatePlanAdminDirectoryList(
            items=[RatePlanAdminDirectoryItem.from_obj(item) for item in items],
            total=total,
            limit=page.limit,
            offset=page.offset,
        )

    if room_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="room_id or sanatorium_id is required",
        )

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


@router.get("/{rate_plan_id}", response_model=RatePlanRead | RatePlanAdminRead)
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
