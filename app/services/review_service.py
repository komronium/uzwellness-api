import uuid
from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal

from fastapi import Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.policies import ReviewPolicy
from app.models.review import SanatoriumReview
from app.models.sanatorium import Sanatorium, SanatoriumStatus
from app.models.user import User
from app.schemas.review import ReviewCreate, ReviewUpdate

_CENTS = Decimal("0.01")


class ReviewService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_reviews(
        self,
        *,
        limit: int,
        offset: int,
        sanatorium_id: uuid.UUID | None = None,
        is_visible: bool | None = None,
        visible_only: bool = True,
    ) -> tuple[Sequence[SanatoriumReview], int]:
        base = select(SanatoriumReview)
        if sanatorium_id is not None:
            base = base.where(SanatoriumReview.sanatorium_id == sanatorium_id)
        if is_visible is not None:
            base = base.where(SanatoriumReview.is_visible.is_(is_visible))
        elif visible_only:
            base = base.where(SanatoriumReview.is_visible.is_(True))

        total = await self.db.scalar(select(func.count()).select_from(base.subquery()))
        stmt = (
            base.order_by(SanatoriumReview.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = (await self.db.scalars(stmt)).all()
        return rows, total or 0

    async def get_by_id(self, review_id: uuid.UUID) -> SanatoriumReview | None:
        return await self.db.get(SanatoriumReview, review_id)

    async def create(
        self, sanatorium_id: uuid.UUID, payload: ReviewCreate, user: User
    ) -> SanatoriumReview:
        sanatorium = await self.db.get(Sanatorium, sanatorium_id)
        if sanatorium is None or sanatorium.status != SanatoriumStatus.APPROVED:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Sanatorium not found"
            )

        review = SanatoriumReview(
            sanatorium_id=sanatorium_id,
            user_id=user.id,
            reviewer_name=payload.reviewer_name,
            reviewer_country=payload.reviewer_country,
            traveler_type=payload.traveler_type,
            rating=payload.rating,
            cleanliness=payload.cleanliness,
            amenities=payload.amenities,
            location=payload.location,
            service=payload.service,
            treatment=payload.treatment,
            value=payload.value,
            food=payload.food,
            body=payload.body,
        )
        self.db.add(review)
        await self.db.flush()
        await self._recompute_rating(sanatorium)
        await self.db.commit()
        await self.db.refresh(review)
        return review

    async def update_visibility(
        self,
        review: SanatoriumReview,
        payload: ReviewUpdate,
        user: User,
    ) -> SanatoriumReview:
        await self._assert_can_moderate(review, user)
        sanatorium = await self._review_sanatorium(review)
        review.is_visible = payload.is_visible
        if sanatorium is not None:
            await self.db.flush()
            await self._recompute_rating(sanatorium)
        await self.db.commit()
        await self.db.refresh(review)
        return review

    async def delete(self, review: SanatoriumReview, user: User) -> None:
        await self._assert_can_delete(review, user)
        sanatorium_id = review.sanatorium_id
        await self.db.delete(review)
        await self.db.flush()
        sanatorium = await self.db.get(Sanatorium, sanatorium_id)
        if sanatorium is not None:
            await self._recompute_rating(sanatorium)
        await self.db.commit()

    async def _assert_can_moderate(self, review: SanatoriumReview, user: User) -> None:
        sanatorium = await self._review_sanatorium(review)
        if not ReviewPolicy.can_moderate(review, user, sanatorium):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not allowed to moderate this review",
            )

    async def _assert_can_delete(self, review: SanatoriumReview, user: User) -> None:
        sanatorium = await self._review_sanatorium(review)
        if not ReviewPolicy.can_delete(review, user, sanatorium):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not allowed to delete this review",
            )

    async def _review_sanatorium(self, review: SanatoriumReview) -> Sanatorium | None:
        return await self.db.get(Sanatorium, review.sanatorium_id)

    async def _recompute_rating(self, sanatorium: Sanatorium) -> None:
        (
            count,
            avg,
            cleanliness,
            amenities,
            location,
            service,
            treatment,
            value,
            food,
        ) = (
            await self.db.execute(
                select(
                    func.count(SanatoriumReview.id),
                    func.avg(SanatoriumReview.rating),
                    func.avg(SanatoriumReview.cleanliness),
                    func.avg(SanatoriumReview.amenities),
                    func.avg(SanatoriumReview.location),
                    func.avg(SanatoriumReview.service),
                    func.avg(SanatoriumReview.treatment),
                    func.avg(SanatoriumReview.value),
                    func.avg(SanatoriumReview.food),
                ).where(
                    SanatoriumReview.sanatorium_id == sanatorium.id,
                    SanatoriumReview.is_visible.is_(True),
                )
            )
        ).one()
        sanatorium.review_count = count or 0
        sanatorium.avg_rating = (
            Decimal(str(avg)).quantize(_CENTS, ROUND_HALF_UP) if avg else None
        )
        sanatorium.rating_breakdown = {
            key: str(Decimal(str(raw)).quantize(_CENTS, ROUND_HALF_UP))
            for key, raw in {
                "cleanliness": cleanliness,
                "amenities": amenities,
                "location": location,
                "service": service,
                "treatment": treatment,
                "value": value,
                "food": food,
            }.items()
            if raw is not None
        }


def get_review_service(db: AsyncSession = Depends(get_db)) -> ReviewService:
    return ReviewService(db)
