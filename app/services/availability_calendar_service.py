import uuid
from datetime import date
from decimal import Decimal

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.permissions import assert_sanatorium_access
from app.core.pricing import calculate_rate_plan_night_price
from app.core.utils import date_range
from app.models.availability import RoomAvailability
from app.models.rate_plan import RatePlan, RatePlanDateRule
from app.models.room import Room
from app.models.user import User
from app.schemas.availability_calendar import (
    AvailabilityCalendarRatePlan,
    AvailabilityCalendarRatePlanDay,
    AvailabilityCalendarRead,
    AvailabilityCalendarRoom,
    AvailabilityCalendarRoomDay,
)


class AvailabilityCalendarService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_calendar(
        self,
        *,
        sanatorium_id: uuid.UUID,
        date_from: date,
        date_to: date,
        user: User,
        room_id: uuid.UUID | None = None,
        rate_plan_ids: list[uuid.UUID] | None = None,
    ) -> AvailabilityCalendarRead:
        if date_from >= date_to:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="date_from must be before date_to",
            )
        await assert_sanatorium_access(
            self.db, sanatorium_id, user, action="view availability calendar"
        )
        dates = date_range(date_from, date_to)
        rooms = await self._rooms(
            sanatorium_id=sanatorium_id,
            room_id=room_id,
            rate_plan_ids=rate_plan_ids,
        )
        availability = await self._availability_map([r.id for r in rooms], dates)
        rules = await self._rule_map(
            [rp.id for room in rooms for rp in room.rate_plans], dates
        )
        return AvailabilityCalendarRead(
            date_from=date_from,
            date_to=date_to,
            rooms=[
                self._room_row(room, dates, availability, rules, rate_plan_ids)
                for room in rooms
            ],
        )

    async def _rooms(
        self,
        *,
        sanatorium_id: uuid.UUID,
        room_id: uuid.UUID | None,
        rate_plan_ids: list[uuid.UUID] | None,
    ) -> list[Room]:
        stmt = (
            select(Room)
            .where(Room.sanatorium_id == sanatorium_id, Room.deleted_at.is_(None))
            .options(
                selectinload(Room.price_periods),
                selectinload(Room.rate_plans).selectinload(RatePlan.amenities),
            )
            .order_by(Room.display_order.asc(), Room.created_at.asc())
        )
        if room_id is not None:
            stmt = stmt.where(Room.id == room_id)
        rooms = list((await self.db.scalars(stmt)).all())
        if room_id is not None and not rooms:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Room not found"
            )
        if rate_plan_ids:
            existing = {rp.id for room in rooms for rp in room.rate_plans}
            missing = set(rate_plan_ids) - existing
            if missing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="rate_plan_ids must belong to the selected sanatorium",
                )
        return rooms

    async def _availability_map(
        self, room_ids: list[uuid.UUID], dates: list[date]
    ) -> dict[tuple[uuid.UUID, date], RoomAvailability]:
        if not room_ids or not dates:
            return {}
        rows = await self.db.scalars(
            select(RoomAvailability).where(
                RoomAvailability.room_id.in_(room_ids),
                RoomAvailability.date.in_(dates),
            )
        )
        return {(row.room_id, row.date): row for row in rows}

    async def _rule_map(
        self, rate_plan_ids: list[uuid.UUID], dates: list[date]
    ) -> dict[tuple[uuid.UUID, date], RatePlanDateRule]:
        if not rate_plan_ids or not dates:
            return {}
        rows = await self.db.scalars(
            select(RatePlanDateRule).where(
                RatePlanDateRule.rate_plan_id.in_(rate_plan_ids),
                RatePlanDateRule.date.in_(dates),
            )
        )
        return {(row.rate_plan_id, row.date): row for row in rows}

    def _room_row(
        self,
        room: Room,
        dates: list[date],
        availability: dict[tuple[uuid.UUID, date], RoomAvailability],
        rules: dict[tuple[uuid.UUID, date], RatePlanDateRule],
        rate_plan_ids: list[uuid.UUID] | None,
    ) -> AvailabilityCalendarRoom:
        room_days = [
            _room_day(room, target, availability.get((room.id, target)))
            for target in dates
        ]
        selected_rate_plans = [
            rp
            for rp in room.rate_plans
            if not rate_plan_ids or rp.id in set(rate_plan_ids)
        ]
        return AvailabilityCalendarRoom(
            id=room.id,
            name=room.name,
            capacity=room.capacity,
            inventory_count=room.inventory_count,
            is_active=room.is_active,
            days=room_days,
            rate_plans=[
                _rate_plan_row(room, rate_plan, room_days, rules)
                for rate_plan in selected_rate_plans
            ],
        )


def _room_day(
    room: Room, target: date, row: RoomAvailability | None
) -> AvailabilityCalendarRoomDay:
    blocked = row.units_blocked if row else 0
    booked = row.units_booked if row else 0
    available = max(room.inventory_count - blocked - booked, 0)
    return AvailabilityCalendarRoomDay(
        date=target,
        room_status="bookable" if room.is_active and available > 0 else "unbookable",
        inventory_count=room.inventory_count,
        units_available=available,
        units_booked=booked,
        units_blocked=blocked,
    )


def _rate_plan_row(
    room: Room,
    rate_plan: RatePlan,
    room_days: list[AvailabilityCalendarRoomDay],
    rules: dict[tuple[uuid.UUID, date], RatePlanDateRule],
) -> AvailabilityCalendarRatePlan:
    return AvailabilityCalendarRatePlan(
        id=rate_plan.id,
        name=rate_plan.name,
        board=rate_plan.board,
        payment_timing=rate_plan.payment_timing,
        confirmation=rate_plan.confirmation,
        board_guests=rate_plan.board_guests,
        days=[
            AvailabilityCalendarRatePlanDay(
                date=day.date,
                is_sellable=(
                    rate_plan.is_active
                    and day.room_status == "bookable"
                    and rules.get((rate_plan.id, day.date), _EMPTY_RULE).is_closed
                    is not True
                ),
                is_closed=rules.get((rate_plan.id, day.date), _EMPTY_RULE).is_closed
                is True,
                selling_rate=_selling_rate(
                    room, rate_plan, day.date, rules.get((rate_plan.id, day.date))
                ),
                currency=room.base_currency,
                min_advance_hours=rules.get(
                    (rate_plan.id, day.date), _EMPTY_RULE
                ).min_advance_hours,
                max_advance_hours=rules.get(
                    (rate_plan.id, day.date), _EMPTY_RULE
                ).max_advance_hours,
                min_stay_nights=rules.get(
                    (rate_plan.id, day.date), _EMPTY_RULE
                ).min_stay_nights,
                min_stay_arrival_nights=rules.get(
                    (rate_plan.id, day.date), _EMPTY_RULE
                ).min_stay_arrival_nights,
            )
            for day in room_days
        ],
    )


def _selling_rate(
    room: Room, rate_plan: RatePlan, target: date, rule: RatePlanDateRule | None
) -> Decimal:
    return calculate_rate_plan_night_price(
        room,
        rate_plan,
        target,
        room.price_periods,
        selling_rate_override=rule.selling_rate if rule else None,
    )


class _EmptyRule:
    is_closed = None
    min_advance_hours = None
    max_advance_hours = None
    min_stay_nights = None
    min_stay_arrival_nights = None


_EMPTY_RULE = _EmptyRule()


def get_availability_calendar_service(
    db: AsyncSession = Depends(get_db),
) -> AvailabilityCalendarService:
    return AvailabilityCalendarService(db)
