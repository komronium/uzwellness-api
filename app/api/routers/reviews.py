import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import CurrentUser, OptionalUser, not_found, require_roles
from app.core.pagination import Pagination
from app.models.review import ReviewReplyStatus, ReviewSource
from app.models.user import UserRole
from app.schemas.review import (
    ReviewAdminSummary,
    ReviewAppealCreate,
    ReviewCreate,
    ReviewList,
    ReviewRead,
    ReviewReplyUpdate,
    ReviewUpdate,
)
from app.services.review_service import ReviewService, get_review_service

router = APIRouter(prefix="/reviews", tags=["Guest Relations"])

require_admin_or_above = require_roles(UserRole.ADMIN, UserRole.SUPER_ADMIN)
ReviewSort = Literal["created_at", "-created_at", "rating", "-rating"]


@router.get("", response_model=ReviewList)
async def list_reviews(
    page: Pagination,
    sanatorium_id: uuid.UUID | None = Query(default=None),
    is_visible: bool | None = Query(default=None),
    source: ReviewSource | None = Query(default=None),
    reply_status: ReviewReplyStatus | None = Query(default=None),
    negative_only: bool = Query(default=False),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    q: str | None = Query(default=None, max_length=200),
    sort: ReviewSort = Query(default="-created_at"),
    current_user: OptionalUser = None,
    reviews: ReviewService = Depends(get_review_service),
) -> ReviewList:
    is_admin = current_user is not None and current_user.role in (
        UserRole.ADMIN,
        UserRole.SUPER_ADMIN,
    )
    if sanatorium_id is None and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="sanatorium_id is required",
        )
    items, total = await reviews.list_reviews(
        sanatorium_id=sanatorium_id,
        is_visible=is_visible if is_admin else None,
        source=source,
        reply_status=reply_status if is_admin else None,
        negative_only=negative_only if is_admin else False,
        date_from=date_from,
        date_to=date_to,
        q=q,
        sort=sort,
        visible_only=not is_admin,
        user=current_user,
        limit=page.limit,
        offset=page.offset,
    )
    return ReviewList(
        items=[ReviewRead.model_validate(r) for r in items],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get(
    "/admin/summary",
    response_model=ReviewAdminSummary,
    dependencies=[Depends(require_admin_or_above)],
)
async def get_review_admin_summary(
    current_user: CurrentUser,
    sanatorium_id: uuid.UUID = Query(...),
    reviews: ReviewService = Depends(get_review_service),
) -> ReviewAdminSummary:
    return await reviews.summary(sanatorium_id=sanatorium_id, user=current_user)


@router.post(
    "/sanatoriums/{sanatorium_id}",
    response_model=ReviewRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_review(
    sanatorium_id: uuid.UUID,
    payload: ReviewCreate,
    current_user: CurrentUser,
    reviews: ReviewService = Depends(get_review_service),
) -> ReviewRead:
    review = await reviews.create(sanatorium_id, payload, current_user)
    return ReviewRead.model_validate(review)


@router.patch(
    "/{review_id}/visibility",
    response_model=ReviewRead,
    dependencies=[Depends(require_admin_or_above)],
)
async def update_review_visibility(
    review_id: uuid.UUID,
    payload: ReviewUpdate,
    current_user: CurrentUser,
    reviews: ReviewService = Depends(get_review_service),
) -> ReviewRead:
    review = await reviews.get_by_id(review_id)
    if review is None:
        raise not_found("Review not found")
    updated = await reviews.update_visibility(review, payload, current_user)
    return ReviewRead.model_validate(updated)


@router.patch(
    "/{review_id}/reply",
    response_model=ReviewRead,
    dependencies=[Depends(require_admin_or_above)],
)
async def reply_to_review(
    review_id: uuid.UUID,
    payload: ReviewReplyUpdate,
    current_user: CurrentUser,
    reviews: ReviewService = Depends(get_review_service),
) -> ReviewRead:
    review = await reviews.get_by_id(review_id)
    if review is None:
        raise not_found("Review not found")
    updated = await reviews.reply(review, payload, current_user)
    return ReviewRead.model_validate(updated)


@router.patch(
    "/{review_id}/appeal",
    response_model=ReviewRead,
    dependencies=[Depends(require_admin_or_above)],
)
async def appeal_review(
    review_id: uuid.UUID,
    payload: ReviewAppealCreate,
    current_user: CurrentUser,
    reviews: ReviewService = Depends(get_review_service),
) -> ReviewRead:
    review = await reviews.get_by_id(review_id)
    if review is None:
        raise not_found("Review not found")
    updated = await reviews.appeal(review, payload, current_user)
    return ReviewRead.model_validate(updated)


@router.delete("/{review_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_review(
    review_id: uuid.UUID,
    current_user: CurrentUser,
    reviews: ReviewService = Depends(get_review_service),
) -> None:
    review = await reviews.get_by_id(review_id)
    if review is None:
        raise not_found("Review not found")
    await reviews.delete(review, current_user)
