import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, LocaleDep, not_found, require_roles
from app.core.pagination import Pagination
from app.models.promotion import PromotionCategory, PromotionStatus
from app.models.user import UserRole
from app.schemas.promotion import (
    PromotionCreate,
    PromotionList,
    PromotionListItem,
    PromotionRead,
    PromotionUpdate,
)
from app.services.promotion_service import PromotionService, get_promotion_service

router = APIRouter(prefix="/promotions", tags=["Promotions"])

require_admin_or_above = require_roles(UserRole.ADMIN, UserRole.SUPER_ADMIN)


@router.get(
    "",
    response_model=PromotionList,
    dependencies=[Depends(require_admin_or_above)],
)
async def list_promotions(
    locale: LocaleDep,
    page: Pagination,
    current_user: CurrentUser,
    sanatorium_id: uuid.UUID = Query(...),
    status_filter: PromotionStatus | None = Query(default=None, alias="status"),
    category: PromotionCategory | None = Query(default=None),
    booking_date_from: date | None = Query(default=None),
    booking_date_to: date | None = Query(default=None),
    promotions: PromotionService = Depends(get_promotion_service),
) -> PromotionList:
    items, total = await promotions.list_for_sanatorium(
        sanatorium_id,
        current_user,
        status_filter=status_filter,
        category=category,
        booking_date_from=booking_date_from,
        booking_date_to=booking_date_to,
        limit=page.limit,
        offset=page.offset,
    )
    return PromotionList(
        items=[
            PromotionListItem.from_obj(
                item,
                locale=locale,
                stats=promotions.stats_for(item),
            )
            for item in items
        ],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get(
    "/{promotion_id}",
    response_model=PromotionRead,
    dependencies=[Depends(require_admin_or_above)],
)
async def get_promotion(
    promotion_id: uuid.UUID,
    locale: LocaleDep,
    current_user: CurrentUser,
    promotions: PromotionService = Depends(get_promotion_service),
) -> PromotionRead:
    promotion = await promotions.get_by_id(promotion_id)
    if promotion is None:
        raise not_found("Promotion not found")
    await promotions.list_for_sanatorium(
        promotion.sanatorium_id,
        current_user,
        status_filter=None,
        category=None,
        booking_date_from=None,
        booking_date_to=None,
        limit=1,
        offset=0,
    )
    return PromotionRead.from_obj(
        promotion,
        locale=locale,
        stats=promotions.stats_for(promotion),
    )


@router.post(
    "",
    response_model=PromotionRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin_or_above)],
)
async def create_promotion(
    payload: PromotionCreate,
    locale: LocaleDep,
    current_user: CurrentUser,
    promotions: PromotionService = Depends(get_promotion_service),
) -> PromotionRead:
    promotion = await promotions.create(payload, current_user)
    return PromotionRead.from_obj(
        promotion,
        locale=locale,
        stats=promotions.stats_for(promotion),
    )


@router.patch(
    "/{promotion_id}",
    response_model=PromotionRead,
    dependencies=[Depends(require_admin_or_above)],
)
async def update_promotion(
    promotion_id: uuid.UUID,
    payload: PromotionUpdate,
    locale: LocaleDep,
    current_user: CurrentUser,
    promotions: PromotionService = Depends(get_promotion_service),
) -> PromotionRead:
    promotion = await promotions.get_by_id(promotion_id)
    if promotion is None:
        raise not_found("Promotion not found")
    updated = await promotions.update(promotion, payload, current_user)
    return PromotionRead.from_obj(
        updated,
        locale=locale,
        stats=promotions.stats_for(updated),
    )


@router.post(
    "/{promotion_id}/pause",
    response_model=PromotionRead,
    dependencies=[Depends(require_admin_or_above)],
)
async def pause_promotion(
    promotion_id: uuid.UUID,
    locale: LocaleDep,
    current_user: CurrentUser,
    promotions: PromotionService = Depends(get_promotion_service),
) -> PromotionRead:
    return await _set_status(
        promotion_id,
        PromotionStatus.PAUSED,
        locale,
        current_user,
        promotions,
    )


@router.post(
    "/{promotion_id}/activate",
    response_model=PromotionRead,
    dependencies=[Depends(require_admin_or_above)],
)
async def activate_promotion(
    promotion_id: uuid.UUID,
    locale: LocaleDep,
    current_user: CurrentUser,
    promotions: PromotionService = Depends(get_promotion_service),
) -> PromotionRead:
    return await _set_status(
        promotion_id,
        PromotionStatus.ACTIVE,
        locale,
        current_user,
        promotions,
    )


@router.post(
    "/{promotion_id}/deactivate",
    response_model=PromotionRead,
    dependencies=[Depends(require_admin_or_above)],
)
async def deactivate_promotion(
    promotion_id: uuid.UUID,
    locale: LocaleDep,
    current_user: CurrentUser,
    promotions: PromotionService = Depends(get_promotion_service),
) -> PromotionRead:
    return await _set_status(
        promotion_id,
        PromotionStatus.INACTIVE,
        locale,
        current_user,
        promotions,
    )


@router.post(
    "/{promotion_id}/duplicate",
    response_model=PromotionRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin_or_above)],
)
async def duplicate_promotion(
    promotion_id: uuid.UUID,
    locale: LocaleDep,
    current_user: CurrentUser,
    promotions: PromotionService = Depends(get_promotion_service),
) -> PromotionRead:
    promotion = await promotions.get_by_id(promotion_id)
    if promotion is None:
        raise not_found("Promotion not found")
    copy = await promotions.duplicate(promotion, current_user)
    return PromotionRead.from_obj(copy, locale=locale, stats=promotions.stats_for(copy))


async def _set_status(
    promotion_id: uuid.UUID,
    status_value: PromotionStatus,
    locale: str,
    current_user,
    promotions: PromotionService,
) -> PromotionRead:
    promotion = await promotions.get_by_id(promotion_id)
    if promotion is None:
        raise not_found("Promotion not found")
    updated = await promotions.set_status(promotion, status_value, current_user)
    return PromotionRead.from_obj(
        updated,
        locale=locale,
        stats=promotions.stats_for(updated),
    )
