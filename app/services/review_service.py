import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal

from fastapi import Depends, HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.policies import ReviewPolicy
from app.models.review import (
    ReviewAppealStatus,
    ReviewReplyStatus,
    ReviewSource,
    SanatoriumReview,
)
from app.models.sanatorium import Sanatorium, SanatoriumStatus
from app.models.user import User, UserRole
from app.schemas.review import (
    ReviewAdminSummary,
    ReviewAppealCreate,
    ReviewCreate,
    ReviewRatingBreakdown,
    ReviewReplyUpdate,
    ReviewTagCount,
    ReviewUpdate,
)

_CENTS = Decimal("0.01")
_NEGATIVE_RATING_MAX = 2


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
        source: ReviewSource | None = None,
        reply_status: ReviewReplyStatus | None = None,
        negative_only: bool = False,
        date_from: date | None = None,
        date_to: date | None = None,
        q: str | None = None,
        sort: str = "-created_at",
        visible_only: bool = True,
        user: User | None = None,
    ) -> tuple[Sequence[SanatoriumReview], int]:
        base = select(SanatoriumReview)
        base = self._apply_visibility_scope(base, user=user)
        if sanatorium_id is not None:
            base = base.where(SanatoriumReview.sanatorium_id == sanatorium_id)
        if is_visible is not None:
            base = base.where(SanatoriumReview.is_visible.is_(is_visible))
        elif visible_only:
            base = base.where(SanatoriumReview.is_visible.is_(True))
        if source is not None:
            base = base.where(SanatoriumReview.source == source)
        if reply_status is not None:
            base = base.where(SanatoriumReview.reply_status == reply_status)
        if negative_only:
            base = base.where(SanatoriumReview.rating <= _NEGATIVE_RATING_MAX)
        if date_from is not None:
            base = base.where(func.date(SanatoriumReview.created_at) >= date_from)
        if date_to is not None:
            base = base.where(func.date(SanatoriumReview.created_at) <= date_to)
        if q and q.strip():
            pattern = f"%{q.strip()}%"
            base = base.where(
                or_(
                    SanatoriumReview.reviewer_name.ilike(pattern),
                    SanatoriumReview.body.ilike(pattern),
                    SanatoriumReview.translated_body.ilike(pattern),
                )
            )

        total = await self.db.scalar(select(func.count()).select_from(base.subquery()))
        stmt = base.order_by(_review_sort_clause(sort)).limit(limit).offset(offset)
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
            booking_id=payload.booking_id,
            room_id=payload.room_id,
            source=payload.source,
            external_id=payload.external_id,
            external_url=payload.external_url,
            reviewer_name=payload.reviewer_name,
            reviewer_country=payload.reviewer_country,
            reviewer_avatar_url=payload.reviewer_avatar_url,
            traveler_type=payload.traveler_type,
            language=payload.language,
            stayed_at=payload.stayed_at,
            stayed_room_name=payload.stayed_room_name,
            rating=payload.rating,
            score_label=payload.score_label,
            cleanliness=payload.cleanliness,
            amenities=payload.amenities,
            location=payload.location,
            service=payload.service,
            treatment=payload.treatment,
            value=payload.value,
            food=payload.food,
            body=payload.body,
            translated_body=payload.translated_body,
            positive_tags=payload.positive_tags,
            negative_tags=payload.negative_tags,
            photos=payload.photos,
        )
        self.db.add(review)
        await self.db.flush()
        await self._recompute_rating(sanatorium)
        await self.db.commit()
        await self.db.refresh(review)
        return review

    async def summary(
        self, *, sanatorium_id: uuid.UUID, user: User
    ) -> ReviewAdminSummary:
        sanatorium = await self.db.get(Sanatorium, sanatorium_id)
        if not ReviewPolicy.can_moderate(
            SanatoriumReview(sanatorium_id=sanatorium_id, user_id=None),
            user,
            sanatorium,
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not allowed to view review analytics",
            )
        rows = (
            await self.db.scalars(
                select(SanatoriumReview).where(
                    SanatoriumReview.sanatorium_id == sanatorium_id
                )
            )
        ).all()
        visible = [item for item in rows if item.is_visible]
        total = len(visible)
        replied = sum(
            item.reply_status == ReviewReplyStatus.REPLIED for item in visible
        )
        return ReviewAdminSummary(
            total_reviews=total,
            awaiting_reply=sum(
                item.reply_status == ReviewReplyStatus.AWAITING_REPLY
                for item in visible
            ),
            negative_reviews=sum(
                item.rating <= _NEGATIVE_RATING_MAX for item in visible
            ),
            reviews_with_photos=sum(bool(item.photos) for item in visible),
            average_rating=_avg([item.rating for item in visible]),
            reply_rate=(
                (Decimal(replied) / Decimal(total) * 100).quantize(
                    _CENTS, ROUND_HALF_UP
                )
                if total
                else Decimal("0.00")
            ),
            rating_breakdown=ReviewRatingBreakdown(
                cleanliness=_avg([item.cleanliness for item in visible]),
                amenities=_avg([item.amenities for item in visible]),
                location=_avg([item.location for item in visible]),
                service=_avg([item.service for item in visible]),
                treatment=_avg([item.treatment for item in visible]),
                value=_avg([item.value for item in visible]),
                food=_avg([item.food for item in visible]),
            ),
            positive_tags=_tag_counts(visible, "positive_tags"),
            negative_tags=_tag_counts(visible, "negative_tags"),
        )

    async def reply(
        self, review: SanatoriumReview, payload: ReviewReplyUpdate, user: User
    ) -> SanatoriumReview:
        await self._assert_can_moderate(review, user)
        review.reply_body = payload.body
        review.reply_language = payload.language
        review.reply_status = ReviewReplyStatus.REPLIED
        review.replied_at = datetime.now(UTC)
        review.replied_by_user_id = user.id
        await self.db.commit()
        await self.db.refresh(review)
        return review

    async def appeal(
        self, review: SanatoriumReview, payload: ReviewAppealCreate, user: User
    ) -> SanatoriumReview:
        await self._assert_can_moderate(review, user)
        review.appeal_status = ReviewAppealStatus.SUBMITTED
        review.appeal_reason = payload.reason
        review.appealed_at = datetime.now(UTC)
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

    def _apply_visibility_scope(self, stmt, *, user: User | None):
        if user is None or user.role not in (UserRole.ADMIN, UserRole.SUPER_ADMIN):
            return stmt
        if user.role == UserRole.SUPER_ADMIN:
            return stmt
        return stmt.where(
            SanatoriumReview.sanatorium_id.in_(
                select(Sanatorium.id).where(Sanatorium.admin_user_id == user.id)
            )
        )

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


def _review_sort_clause(sort: str):
    return {
        "created_at": SanatoriumReview.created_at.asc(),
        "-created_at": SanatoriumReview.created_at.desc(),
        "rating": SanatoriumReview.rating.asc(),
        "-rating": SanatoriumReview.rating.desc(),
    }.get(sort, SanatoriumReview.created_at.desc())


def _avg(values: list[int | None]) -> Decimal | None:
    cleaned = [Decimal(value) for value in values if value is not None]
    if not cleaned:
        return None
    return (sum(cleaned) / Decimal(len(cleaned))).quantize(_CENTS, ROUND_HALF_UP)


def _tag_counts(
    reviews: Sequence[SanatoriumReview], field: str
) -> list[ReviewTagCount]:
    counts: dict[str, int] = {}
    for review in reviews:
        for tag in getattr(review, field) or []:
            if isinstance(tag, str):
                counts[tag] = counts.get(tag, 0) + 1
            elif isinstance(tag, dict) and tag.get("tag"):
                key = str(tag["tag"])
                counts[key] = counts.get(key, 0) + int(tag.get("count", 1))
    return [
        ReviewTagCount(tag=tag, count=count)
        for tag, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]
