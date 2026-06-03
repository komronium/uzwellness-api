import uuid
from collections.abc import Sequence
from datetime import date

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.pagination import paginated
from app.core.permissions import assert_sanatorium_access
from app.core.utils import merge_translation_fields
from app.models.promotion import Promotion, PromotionCategory, PromotionStatus
from app.models.rate_plan import RatePlan
from app.models.user import User
from app.schemas.promotion import PromotionCreate, PromotionStats, PromotionUpdate

_ACTION = "manage this sanatorium's promotions"


class PromotionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, promotion_id: uuid.UUID) -> Promotion | None:
        return await self.db.scalar(
            select(Promotion)
            .options(
                selectinload(Promotion.rate_plans).selectinload(RatePlan.room),
            )
            .where(Promotion.id == promotion_id)
        )

    async def list_for_sanatorium(
        self,
        sanatorium_id: uuid.UUID,
        user: User,
        *,
        status_filter: PromotionStatus | None,
        category: PromotionCategory | None,
        booking_date_from: date | None,
        booking_date_to: date | None,
        limit: int,
        offset: int,
    ) -> tuple[Sequence[Promotion], int]:
        await assert_sanatorium_access(self.db, sanatorium_id, user, action=_ACTION)
        stmt = (
            select(Promotion)
            .where(Promotion.sanatorium_id == sanatorium_id)
            .order_by(Promotion.created_at.desc())
        )
        if status_filter is not None:
            stmt = stmt.where(Promotion.status == status_filter)
        if category is not None:
            stmt = stmt.where(Promotion.category == category)
        if booking_date_from is not None:
            stmt = stmt.where(
                (Promotion.booking_date_to.is_(None))
                | (Promotion.booking_date_to >= booking_date_from)
            )
        if booking_date_to is not None:
            stmt = stmt.where(
                (Promotion.booking_date_from.is_(None))
                | (Promotion.booking_date_from <= booking_date_to)
            )
        return await paginated(self.db, stmt, limit=limit, offset=offset)

    async def create(self, payload: PromotionCreate, user: User) -> Promotion:
        await assert_sanatorium_access(
            self.db, payload.sanatorium_id, user, action=_ACTION
        )
        promotion = Promotion(
            sanatorium_id=payload.sanatorium_id,
            name=payload.name.model_dump(),
            category=payload.category,
            status=payload.status,
            discount_percent=payload.discount_percent,
            booking_date_from=payload.booking_date_from,
            booking_date_to=payload.booking_date_to,
            stay_date_from=payload.stay_date_from,
            stay_date_to=payload.stay_date_to,
            booking_weekdays=payload.booking_weekdays,
            stay_weekdays=payload.stay_weekdays,
            booking_time_from=payload.booking_time_from,
            booking_time_to=payload.booking_time_to,
            audience=payload.audience,
            cancellation_policy_mode=payload.cancellation_policy_mode,
            custom_cancellation_policy=payload.custom_cancellation_policy,
            pay_with_cost_per_sale_account=payload.pay_with_cost_per_sale_account,
            rate_plans=await self._rate_plans(
                payload.sanatorium_id, payload.rate_plan_ids
            ),
        )
        self.db.add(promotion)
        await self.db.commit()
        await self.db.refresh(promotion)
        return await self._fresh(promotion.id)

    async def update(
        self, promotion: Promotion, payload: PromotionUpdate, user: User
    ) -> Promotion:
        await assert_sanatorium_access(
            self.db, promotion.sanatorium_id, user, action=_ACTION
        )
        data = payload.model_dump(exclude_unset=True)
        rate_plan_ids = data.pop("rate_plan_ids", None)
        merge_translation_fields(promotion, data, ("name",))
        for field, value in data.items():
            setattr(promotion, field, value)
        if rate_plan_ids is not None:
            promotion.rate_plans = await self._rate_plans(
                promotion.sanatorium_id, rate_plan_ids
            )
        await self.db.commit()
        await self.db.refresh(promotion)
        return await self._fresh(promotion.id)

    async def set_status(
        self, promotion: Promotion, status_value: PromotionStatus, user: User
    ) -> Promotion:
        await assert_sanatorium_access(
            self.db, promotion.sanatorium_id, user, action=_ACTION
        )
        promotion.status = status_value
        await self.db.commit()
        await self.db.refresh(promotion)
        return await self._fresh(promotion.id)

    async def duplicate(self, promotion: Promotion, user: User) -> Promotion:
        await assert_sanatorium_access(
            self.db, promotion.sanatorium_id, user, action=_ACTION
        )
        copy = Promotion(
            sanatorium_id=promotion.sanatorium_id,
            name=_copy_name(promotion.name),
            category=promotion.category,
            status=PromotionStatus.PAUSED,
            discount_percent=promotion.discount_percent,
            booking_date_from=promotion.booking_date_from,
            booking_date_to=promotion.booking_date_to,
            stay_date_from=promotion.stay_date_from,
            stay_date_to=promotion.stay_date_to,
            booking_weekdays=promotion.booking_weekdays,
            stay_weekdays=promotion.stay_weekdays,
            booking_time_from=promotion.booking_time_from,
            booking_time_to=promotion.booking_time_to,
            audience=promotion.audience,
            cancellation_policy_mode=promotion.cancellation_policy_mode,
            custom_cancellation_policy=promotion.custom_cancellation_policy,
            pay_with_cost_per_sale_account=promotion.pay_with_cost_per_sale_account,
            rate_plans=list(promotion.rate_plans),
        )
        self.db.add(copy)
        await self.db.commit()
        await self.db.refresh(copy)
        return await self._fresh(copy.id)

    def stats_for(self, promotion: Promotion) -> PromotionStats:
        return PromotionStats()

    async def _rate_plans(
        self, sanatorium_id: uuid.UUID, rate_plan_ids: list[uuid.UUID]
    ) -> list[RatePlan]:
        if not rate_plan_ids:
            return []
        rate_plans = list(
            (
                await self.db.scalars(
                    select(RatePlan)
                    .options(selectinload(RatePlan.room))
                    .where(RatePlan.id.in_(rate_plan_ids))
                )
            ).all()
        )
        if len({rate_plan.id for rate_plan in rate_plans}) != len(set(rate_plan_ids)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="One or more rate_plan IDs not found",
            )
        if any(
            rate_plan.room.sanatorium_id != sanatorium_id for rate_plan in rate_plans
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="rate_plan_ids must belong to the selected sanatorium",
            )
        return rate_plans

    async def _fresh(self, promotion_id: uuid.UUID) -> Promotion:
        promotion = await self.get_by_id(promotion_id)
        if promotion is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Promotion not found"
            )
        return promotion


def _copy_name(name: dict) -> dict:
    return {lang: f"{value} Copy" if value else value for lang, value in name.items()}


def get_promotion_service(db: AsyncSession = Depends(get_db)) -> PromotionService:
    return PromotionService(db)
