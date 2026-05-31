import uuid
from collections.abc import Sequence

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.db_utils import fetch_by_ids
from app.core.pagination import paginated
from app.core.permissions import assert_sanatorium_access
from app.core.utils import merge_translation_fields
from app.models.amenity import Amenity
from app.models.rate_plan import BoardType, RatePlan
from app.models.room import Room
from app.models.user import User
from app.schemas.rate_plan import RatePlanCreate, RatePlanUpdate

_ACTION = "manage this sanatorium's rate plans"


class RatePlanService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, rate_plan_id: uuid.UUID) -> RatePlan | None:
        return await self.db.scalar(
            select(RatePlan)
            .options(selectinload(RatePlan.amenities))
            .where(RatePlan.id == rate_plan_id)
        )

    async def list_for_room(
        self, room_id: uuid.UUID, *, limit: int, offset: int
    ) -> tuple[Sequence[RatePlan], int]:
        stmt = (
            select(RatePlan)
            .options(selectinload(RatePlan.amenities))
            .where(RatePlan.room_id == room_id)
            .order_by(RatePlan.created_at.asc())
        )
        return await paginated(self.db, stmt, limit=limit, offset=offset)

    async def create(self, payload: RatePlanCreate, user: User) -> RatePlan:
        room = await self.db.get(Room, payload.room_id)
        if room is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Room not found"
            )
        await assert_sanatorium_access(
            self.db, room.sanatorium_id, user, action=_ACTION
        )
        self._validate(
            board=payload.board,
            board_optional=payload.board_optional,
            board_price=payload.board_price,
            min_nights=payload.min_nights,
            max_nights=payload.max_nights,
        )

        rate_plan = RatePlan(
            room_id=payload.room_id,
            name=payload.name.model_dump(),
            board=payload.board,
            board_optional=payload.board_optional,
            board_price=payload.board_price,
            board_guests=payload.board_guests,
            refundable=payload.refundable,
            free_cancellation_days=payload.free_cancellation_days,
            cancellation_penalty_percent=payload.cancellation_penalty_percent,
            cancellation_penalty_amount=payload.cancellation_penalty_amount,
            payment_timing=payload.payment_timing,
            confirmation=payload.confirmation,
            price_adjustment_percent=payload.price_adjustment_percent,
            promo_label=payload.promo_label,
            promo_percent=payload.promo_percent,
            promo_starts_at=payload.promo_starts_at,
            promo_ends_at=payload.promo_ends_at,
            min_nights=payload.min_nights,
            max_nights=payload.max_nights,
            amenities=await fetch_by_ids(
                self.db, Amenity, payload.amenity_ids, label="amenity"
            ),
        )
        self.db.add(rate_plan)
        await self.db.commit()
        await self.db.refresh(rate_plan)
        return rate_plan

    async def update(
        self, rate_plan: RatePlan, payload: RatePlanUpdate, user: User
    ) -> RatePlan:
        room = await self.db.get(Room, rate_plan.room_id)
        if room is not None:
            await assert_sanatorium_access(
                self.db, room.sanatorium_id, user, action=_ACTION
            )

        data = payload.model_dump(exclude_unset=True)
        amenity_ids = data.pop("amenity_ids", None)
        merge_translation_fields(rate_plan, data, ("name",))
        self._validate(
            board=data.get("board", rate_plan.board),
            board_optional=data.get("board_optional", rate_plan.board_optional),
            board_price=data.get("board_price", rate_plan.board_price),
            min_nights=data.get("min_nights", rate_plan.min_nights),
            max_nights=data.get("max_nights", rate_plan.max_nights),
        )

        for field, value in data.items():
            setattr(rate_plan, field, value)
        if amenity_ids is not None:
            rate_plan.amenities = await fetch_by_ids(
                self.db, Amenity, amenity_ids, label="amenity"
            )
        await self.db.commit()
        await self.db.refresh(rate_plan)
        return rate_plan

    async def delete(self, rate_plan: RatePlan, user: User) -> None:
        room = await self.db.get(Room, rate_plan.room_id)
        if room is not None:
            await assert_sanatorium_access(
                self.db, room.sanatorium_id, user, action=_ACTION
            )
        await self.db.delete(rate_plan)
        await self.db.commit()

    @staticmethod
    def _validate(
        *,
        board: BoardType,
        board_optional: bool,
        board_price,
        min_nights: int | None,
        max_nights: int | None,
    ) -> None:
        if board == BoardType.ROOM_ONLY and (board_optional or board_price is not None):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="room_only board cannot have a board price",
            )
        if board_optional and board_price is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="board_price is required when board_optional is true",
            )
        if not board_optional and board_price is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="board_price is only allowed when board_optional is true",
            )
        if (
            min_nights is not None
            and max_nights is not None
            and max_nights < min_nights
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="max_nights must be >= min_nights",
            )


def get_rate_plan_service(db: AsyncSession = Depends(get_db)) -> RatePlanService:
    return RatePlanService(db)
