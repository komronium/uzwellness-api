import uuid
from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal

from fastapi import Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.review import SanatoriumReview
from app.models.sanatorium import Sanatorium
from app.models.user import User, UserRole
from app.schemas.review import ReviewCreate, ReviewUpdate

_TWO = Decimal("0.01")


class ReviewService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_for_sanatorium(
        self,
        sanatorium_id: uuid.UUID,
        *,
        limit: int,
        offset: int,
        visible_only: bool = True,
    ) -> tuple[Sequence[SanatoriumReview], int]:
        base = select(SanatoriumReview).where(SanatoriumReview.sanatorium_id == sanatorium_id)
        if visible_only:
            base = base.where(SanatoriumReview.is_visible.is_(True))

        total = (await self.db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
        rows = (await self.db.execute(
            base.order_by(SanatoriumReview.created_at.desc()).limit(limit).offset(offset)
        )).scalars().all()
        return rows, total

    async def create(
        self, sanatorium_id: uuid.UUID, payload: ReviewCreate, user: User
    ) -> SanatoriumReview:
        sanatorium = (await self.db.execute(
            select(Sanatorium).where(Sanatorium.id == sanatorium_id)
        )).scalar_one_or_none()
        if sanatorium is None or sanatorium.status.value != "approved":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sanatorium not found")

        review = SanatoriumReview(
            sanatorium_id=sanatorium_id,
            user_id=user.id,
            reviewer_name=payload.reviewer_name,
            reviewer_country=payload.reviewer_country,
            rating=payload.rating,
            body=payload.body,
        )
        self.db.add(review)
        await self.db.flush()

        await self._update_sanatorium_rating(sanatorium)
        await self.db.commit()
        await self.db.refresh(review)
        return review

    async def get_by_id(self, review_id: uuid.UUID) -> SanatoriumReview | None:
        return (await self.db.execute(
            select(SanatoriumReview).where(SanatoriumReview.id == review_id)
        )).scalar_one_or_none()

    async def update_visibility(
        self, review: SanatoriumReview, payload: ReviewUpdate, user: User
    ) -> SanatoriumReview:
        if user.role not in (UserRole.ADMIN, UserRole.SUPER_ADMIN):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        if user.role == UserRole.ADMIN:
            sanatorium = (await self.db.execute(
                select(Sanatorium).where(Sanatorium.id == review.sanatorium_id)
            )).scalar_one_or_none()
            if sanatorium is None or sanatorium.admin_user_id != user.id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your sanatorium")

        review.is_visible = payload.is_visible
        await self.db.commit()
        await self.db.refresh(review)
        return review

    async def delete(self, review: SanatoriumReview, user: User) -> None:
        if user.role == UserRole.SUPER_ADMIN:
            pass
        elif user.role == UserRole.ADMIN:
            sanatorium = (await self.db.execute(
                select(Sanatorium).where(Sanatorium.id == review.sanatorium_id)
            )).scalar_one_or_none()
            if sanatorium is None or sanatorium.admin_user_id != user.id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your sanatorium")
        elif review.user_id != user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your review")

        sanatorium_id = review.sanatorium_id
        await self.db.delete(review)
        await self.db.flush()

        sanatorium = (await self.db.execute(
            select(Sanatorium).where(Sanatorium.id == sanatorium_id)
        )).scalar_one_or_none()
        if sanatorium:
            await self._update_sanatorium_rating(sanatorium)
        await self.db.commit()

    async def _update_sanatorium_rating(self, sanatorium: Sanatorium) -> None:
        row = (await self.db.execute(
            select(
                func.count(SanatoriumReview.id),
                func.avg(SanatoriumReview.rating),
            ).where(
                SanatoriumReview.sanatorium_id == sanatorium.id,
                SanatoriumReview.is_visible.is_(True),
            )
        )).one()
        count, avg = row
        sanatorium.review_count = count or 0
        sanatorium.avg_rating = (
            Decimal(str(avg)).quantize(_TWO, ROUND_HALF_UP) if avg else None
        )


def get_review_service(db: AsyncSession = Depends(get_db)) -> ReviewService:
    return ReviewService(db)
