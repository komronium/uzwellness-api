import uuid
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import (
    APIRouter,
    Depends,
    Path,
    Query,
    status,
)

from app.api.deps import (
    CurrentUser,
    IncludeTranslationsDep,
    LocaleDep,
    OptionalUser,
    not_found,
    require_roles,
)
from app.core.pagination import Pagination
from app.api.routers.sanatorium_access import ensure_can_edit_sanatorium
from app.api.sanatorium_mapping import (
    sanatorium_admin_list,
    sanatorium_admin_read,
    sanatorium_list,
    sanatorium_public_read,
)
from app.models.sanatorium import PropertyType, SanatoriumStatus, WellnessCategory
from app.models.user import User, UserRole
from app.schemas.sanatorium import (
    SanatoriumAdminList,
    SanatoriumAdminRead,
    SanatoriumCreate,
    SanatoriumList,
    SanatoriumRead,
    SanatoriumUpdate,
)
from app.schemas.sanatorium_content import SanatoriumContentOverview
from app.schemas.sanatorium_policies import SanatoriumPolicies, SanatoriumPoliciesUpdate
from app.schemas.sanatorium_reservation import (
    SanatoriumReservationSettingsRead,
    SanatoriumReservationSettingsUpdate,
)
from app.services.sanatorium_content_service import (
    SanatoriumContentService,
    get_sanatorium_content_service,
)
from app.services.sanatorium_service import (
    SanatoriumService,
    get_sanatorium_service,
)
from app.services.sanatorium_query_service import (
    SanatoriumQueryService,
    get_sanatorium_query_service,
)

router = APIRouter(prefix="/sanatoriums", tags=["Sanatoriums"])

require_admin_or_above = require_roles(UserRole.ADMIN, UserRole.SUPER_ADMIN)
require_super_admin = require_roles(UserRole.SUPER_ADMIN)


SortField = Literal[
    "name", "-name", "stars", "-stars", "rating", "-rating", "created_at", "-created_at"
]


@router.get("", response_model=SanatoriumList | SanatoriumAdminList)
async def list_sanatoriums(
    current_user: OptionalUser,
    locale: LocaleDep,
    include_translations: IncludeTranslationsDep,
    page: Pagination,
    sanatoriums: SanatoriumQueryService = Depends(get_sanatorium_query_service),
    city: str | None = Query(default=None, max_length=120),
    region_id: uuid.UUID | None = Query(default=None),
    destination_id: uuid.UUID | None = Query(default=None),
    status_filter: SanatoriumStatus | None = Query(default=None, alias="status"),
    stars: int | None = Query(default=None, ge=1, le=5),
    min_rating: Decimal | None = Query(default=None, ge=0, le=5),
    q: str | None = Query(default=None, max_length=200),
    sort: SortField = Query(default="-created_at"),
    amenity_ids: Annotated[list[uuid.UUID] | None, Query()] = None,
    treatment_focus: str | None = Query(default=None, max_length=60),
    property_type: PropertyType | None = Query(default=None),
    wellness_category: WellnessCategory | None = Query(default=None),
) -> SanatoriumList | SanatoriumAdminList:
    items, total = await sanatoriums.list_for_user(
        user=current_user,
        limit=page.limit,
        offset=page.offset,
        city=city,
        region_id=region_id,
        destination_id=destination_id,
        status_filter=status_filter,
        stars=stars,
        min_rating=min_rating,
        q=q,
        sort=sort,
        locale=locale,
        amenity_ids=amenity_ids,
        treatment_focus=treatment_focus,
        property_type=property_type,
        wellness_category=wellness_category,
    )
    if include_translations:
        return sanatorium_admin_list(
            items, total=total, limit=page.limit, offset=page.offset
        )
    return sanatorium_list(
        items, total=total, limit=page.limit, offset=page.offset, locale=locale
    )


@router.get("/slug/{slug}", response_model=SanatoriumRead | SanatoriumAdminRead)
async def get_sanatorium_by_slug(
    slug: Annotated[str, Path(min_length=1, max_length=255)],
    current_user: OptionalUser,
    locale: LocaleDep,
    include_translations: IncludeTranslationsDep,
    sanatoriums: SanatoriumQueryService = Depends(get_sanatorium_query_service),
) -> SanatoriumRead | SanatoriumAdminRead:
    sanatorium = await sanatoriums.get_visible_by_slug(slug, current_user)
    if sanatorium is None:
        raise not_found("Sanatorium not found")
    if include_translations:
        return sanatorium_admin_read(sanatorium)
    return sanatorium_public_read(sanatorium, locale=locale)


@router.get(
    "/{sanatorium_id}/content-overview",
    response_model=SanatoriumContentOverview,
    dependencies=[Depends(require_admin_or_above)],
)
async def get_sanatorium_content_overview(
    sanatorium_id: uuid.UUID,
    current_user: CurrentUser,
    locale: LocaleDep,
    sanatoriums: SanatoriumQueryService = Depends(get_sanatorium_query_service),
    content: SanatoriumContentService = Depends(get_sanatorium_content_service),
) -> SanatoriumContentOverview:
    sanatorium = await sanatoriums.get_by_id(sanatorium_id)
    if sanatorium is None:
        raise not_found("Sanatorium not found")
    return await content.overview(sanatorium, current_user, locale=locale)


@router.get(
    "/{sanatorium_id}/policies",
    response_model=SanatoriumPolicies,
    dependencies=[Depends(require_admin_or_above)],
)
async def get_sanatorium_policies(
    sanatorium_id: uuid.UUID,
    current_user: CurrentUser,
    sanatoriums: SanatoriumService = Depends(get_sanatorium_service),
) -> SanatoriumPolicies:
    sanatorium = await sanatoriums.get_by_id(sanatorium_id)
    if sanatorium is None:
        raise not_found("Sanatorium not found")
    ensure_can_edit_sanatorium(sanatorium, current_user)
    return SanatoriumPolicies.model_validate(sanatorium.policies or {})


@router.patch(
    "/{sanatorium_id}/policies",
    response_model=SanatoriumPolicies,
    dependencies=[Depends(require_admin_or_above)],
)
async def update_sanatorium_policies(
    sanatorium_id: uuid.UUID,
    payload: SanatoriumPoliciesUpdate,
    current_user: CurrentUser,
    sanatoriums: SanatoriumService = Depends(get_sanatorium_service),
) -> SanatoriumPolicies:
    sanatorium = await sanatoriums.get_by_id(sanatorium_id)
    if sanatorium is None:
        raise not_found("Sanatorium not found")
    ensure_can_edit_sanatorium(sanatorium, current_user)
    updated = await sanatoriums.update_policies(sanatorium, payload)
    return SanatoriumPolicies.model_validate(updated.policies or {})


@router.get("/{sanatorium_id}", response_model=SanatoriumRead | SanatoriumAdminRead)
async def get_sanatorium(
    sanatorium_id: uuid.UUID,
    current_user: OptionalUser,
    locale: LocaleDep,
    include_translations: IncludeTranslationsDep,
    sanatoriums: SanatoriumQueryService = Depends(get_sanatorium_query_service),
) -> SanatoriumRead | SanatoriumAdminRead:
    sanatorium = await sanatoriums.get_visible(sanatorium_id, current_user)
    if sanatorium is None:
        raise not_found("Sanatorium not found")
    if include_translations:
        return sanatorium_admin_read(sanatorium)
    return sanatorium_public_read(sanatorium, locale=locale)


@router.post(
    "",
    response_model=SanatoriumAdminRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_sanatorium(
    payload: SanatoriumCreate,
    current_user: User = Depends(require_admin_or_above),
    sanatoriums: SanatoriumService = Depends(get_sanatorium_service),
) -> SanatoriumAdminRead:
    # Admins always own the sanatorium they create; only super_admin may
    # explicitly assign it to a different admin.
    if current_user.role == UserRole.ADMIN:
        payload = payload.model_copy(update={"admin_user_id": current_user.id})
    sanatorium = await sanatoriums.create(payload)
    return sanatorium_admin_read(sanatorium)


@router.patch("/{sanatorium_id}", response_model=SanatoriumAdminRead)
async def update_sanatorium(
    sanatorium_id: uuid.UUID,
    payload: SanatoriumUpdate,
    current_user: CurrentUser,
    sanatoriums: SanatoriumService = Depends(get_sanatorium_service),
) -> SanatoriumAdminRead:
    sanatorium = await sanatoriums.get_by_id(sanatorium_id)
    if sanatorium is None:
        raise not_found("Sanatorium not found")
    ensure_can_edit_sanatorium(sanatorium, current_user)
    updated = await sanatoriums.update(sanatorium, payload, actor=current_user)
    return sanatorium_admin_read(updated)


@router.get(
    "/{sanatorium_id}/reservation-settings",
    response_model=SanatoriumReservationSettingsRead,
)
async def get_reservation_settings(
    sanatorium_id: uuid.UUID,
    current_user: CurrentUser,
    sanatoriums: SanatoriumService = Depends(get_sanatorium_service),
) -> SanatoriumReservationSettingsRead:
    sanatorium = await sanatoriums.get_by_id(sanatorium_id)
    if sanatorium is None:
        raise not_found("Sanatorium not found")
    ensure_can_edit_sanatorium(sanatorium, current_user)
    return SanatoriumReservationSettingsRead.model_validate(sanatorium)


@router.patch(
    "/{sanatorium_id}/reservation-settings",
    response_model=SanatoriumReservationSettingsRead,
)
async def update_reservation_settings(
    sanatorium_id: uuid.UUID,
    payload: SanatoriumReservationSettingsUpdate,
    current_user: CurrentUser,
    sanatoriums: SanatoriumService = Depends(get_sanatorium_service),
) -> SanatoriumReservationSettingsRead:
    sanatorium = await sanatoriums.get_by_id(sanatorium_id)
    if sanatorium is None:
        raise not_found("Sanatorium not found")
    ensure_can_edit_sanatorium(sanatorium, current_user)
    updated = await sanatoriums.update_reservation_settings(sanatorium, payload)
    return SanatoriumReservationSettingsRead.model_validate(updated)


@router.post(
    "/{sanatorium_id}/approve",
    response_model=SanatoriumAdminRead,
    dependencies=[Depends(require_super_admin)],
)
async def approve_sanatorium(
    sanatorium_id: uuid.UUID,
    sanatoriums: SanatoriumService = Depends(get_sanatorium_service),
) -> SanatoriumAdminRead:
    sanatorium = await sanatoriums.get_by_id(sanatorium_id)
    if sanatorium is None:
        raise not_found("Sanatorium not found")
    approved = await sanatoriums.approve(sanatorium)
    return sanatorium_admin_read(approved)


@router.post(
    "/{sanatorium_id}/reject",
    response_model=SanatoriumAdminRead,
    dependencies=[Depends(require_super_admin)],
)
async def reject_sanatorium(
    sanatorium_id: uuid.UUID,
    sanatoriums: SanatoriumService = Depends(get_sanatorium_service),
) -> SanatoriumAdminRead:
    sanatorium = await sanatoriums.get_by_id(sanatorium_id)
    if sanatorium is None:
        raise not_found("Sanatorium not found")
    rejected = await sanatoriums.reject(sanatorium)
    return sanatorium_admin_read(rejected)
