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
from app.models.availability_log import (
    AvailabilityLogCategory,
    AvailabilityOperationLog,
)
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
            .join(Room, RatePlan.room_id == Room.id)
            .options(selectinload(RatePlan.amenities))
            .where(RatePlan.room_id == room_id, Room.deleted_at.is_(None))
            .order_by(RatePlan.created_at.asc())
        )
        return await paginated(self.db, stmt, limit=limit, offset=offset)

    async def list_for_sanatorium(
        self,
        sanatorium_id: uuid.UUID,
        user: User,
        *,
        room_id: uuid.UUID | None,
        rate_plan_ids: list[uuid.UUID] | None,
        hide_inactive: bool,
        limit: int,
        offset: int,
    ) -> tuple[Sequence[RatePlan], int]:
        await assert_sanatorium_access(self.db, sanatorium_id, user, action=_ACTION)

        stmt = (
            select(RatePlan)
            .join(Room, RatePlan.room_id == Room.id)
            .options(selectinload(RatePlan.amenities), selectinload(RatePlan.room))
            .where(Room.sanatorium_id == sanatorium_id, Room.deleted_at.is_(None))
            .order_by(
                RatePlan.is_active.desc(),
                Room.created_at.asc(),
                RatePlan.created_at.asc(),
            )
        )
        if room_id is not None:
            stmt = stmt.where(Room.id == room_id)
        if rate_plan_ids:
            stmt = stmt.where(RatePlan.id.in_(rate_plan_ids))
        if hide_inactive:
            stmt = stmt.where(RatePlan.is_active.is_(True), Room.is_active.is_(True))

        return await paginated(self.db, stmt, limit=limit, offset=offset)

    async def create(self, payload: RatePlanCreate, user: User) -> RatePlan:
        room = await self.db.get(Room, payload.room_id)
        if room is None or room.deleted_at is not None:
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
        cancellation_before = _cancellation_snapshot(rate_plan)
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
        if room is not None and _touches_cancellation_policy(data):
            self.db.add(
                AvailabilityOperationLog(
                    sanatorium_id=room.sanatorium_id,
                    room_id=room.id,
                    rate_plan_id=rate_plan.id,
                    operated_by_id=user.id,
                    category=AvailabilityLogCategory.CANCELLATION_POLICY,
                    action="update_cancellation_policy",
                    before=cancellation_before,
                    after=_cancellation_snapshot(rate_plan),
                )
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


_CANCELLATION_FIELDS = frozenset(
    {
        "refundable",
        "free_cancellation_days",
        "cancellation_penalty_percent",
        "cancellation_penalty_amount",
    }
)


def _touches_cancellation_policy(data: dict) -> bool:
    return bool(_CANCELLATION_FIELDS & data.keys())


def _cancellation_snapshot(rate_plan: RatePlan) -> dict:
    return {
        "refundable": rate_plan.refundable,
        "free_cancellation_days": rate_plan.free_cancellation_days,
        "cancellation_penalty_percent": (
            str(rate_plan.cancellation_penalty_percent)
            if rate_plan.cancellation_penalty_percent is not None
            else None
        ),
        "cancellation_penalty_amount": (
            str(rate_plan.cancellation_penalty_amount)
            if rate_plan.cancellation_penalty_amount is not None
            else None
        ),
    }
