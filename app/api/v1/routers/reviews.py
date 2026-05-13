import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import CurrentUser, OptionalUser, require_roles
from app.models.user import UserRole
from app.schemas.review import ReviewCreate, ReviewList, ReviewRead, ReviewUpdate
from app.services.review_service import ReviewService, get_review_service

router = APIRouter(prefix="/reviews", tags=["reviews"])

require_admin_or_above = require_roles(UserRole.ADMIN, UserRole.SUPER_ADMIN)


@router.get("", response_model=ReviewList)
async def list_reviews(
    sanatorium_id: uuid.UUID = Query(...),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: OptionalUser = None,
    svc: ReviewService = Depends(get_review_service),
) -> ReviewList:
    visible_only = current_user is None or current_user.role not in (
        UserRole.ADMIN, UserRole.SUPER_ADMIN
    )
    items, total = await svc.list_for_sanatorium(
        sanatorium_id, limit=limit, offset=offset, visible_only=visible_only
    )
    return ReviewList(items=list(items), total=total, limit=limit, offset=offset)


@router.post(
    "/sanatoriums/{sanatorium_id}",
    response_model=ReviewRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_review(
    sanatorium_id: uuid.UUID,
    payload: ReviewCreate,
    current_user: CurrentUser,
    svc: ReviewService = Depends(get_review_service),
) -> ReviewRead:
    review = await svc.create(sanatorium_id, payload, current_user)
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
    svc: ReviewService = Depends(get_review_service),
) -> ReviewRead:
    review = await svc.get_by_id(review_id)
    if review is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found")
    updated = await svc.update_visibility(review, payload, current_user)
    return ReviewRead.model_validate(updated)


@router.delete("/{review_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_review(
    review_id: uuid.UUID,
    current_user: CurrentUser,
    svc: ReviewService = Depends(get_review_service),
) -> None:
    review = await svc.get_by_id(review_id)
    if review is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found")
    await svc.delete(review, current_user)
