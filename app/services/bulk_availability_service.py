import uuid
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

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
from app.schemas.bulk_availability import (
    BulkAllotmentUpdate,
    BulkCopyRates,
    BulkOperationResult,
    BulkRatesUpdate,
    BulkRestrictionsUpdate,
    BulkRoomStatusUpdate,
    CopyRateAdjustment,
    CopyRateAlignment,
)


class BulkAvailabilityService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def update_allotment(
        self, payload: BulkAllotmentUpdate, user: User
    ) -> BulkOperationResult:
        rate_plans = await self._rate_plans(
            payload.sanatorium_id, payload.rate_plan_ids
        )
        await assert_sanatorium_access(
            self.db, payload.sanatorium_id, user, action="bulk edit availability"
        )
        dates = _scope_dates(payload.date_ranges, payload.weekdays)
        rooms = {rate_plan.room for rate_plan in rate_plans}
        updated = 0
        for room in rooms:
            existing = await self._availability(room.id, dates)
            for target in dates:
                row = existing.get(target)
                booked = row.units_booked if row else 0
                if not payload.allow_overbooking and payload.units_available > (
                    room.inventory_count - booked
                ):
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=(
                            f"units_available exceeds remaining inventory on {target}"
                        ),
                    )
                units_blocked = max(
                    room.inventory_count - booked - payload.units_available, 0
                )
                self._set_availability(row, room, target, units_blocked)
                updated += 1
        await self.db.commit()
        return BulkOperationResult(updated=updated)

    async def update_rates(
        self, payload: BulkRatesUpdate, user: User
    ) -> BulkOperationResult:
        rate_plans = await self._rate_plans(
            payload.sanatorium_id, payload.rate_plan_ids
        )
        await assert_sanatorium_access(
            self.db, payload.sanatorium_id, user, action="bulk edit rates"
        )
        dates = _scope_dates(payload.date_ranges, payload.weekdays)
        rules = await self._rules([rp.id for rp in rate_plans], dates)
        updated = 0
        for rate_plan in rate_plans:
            for target in dates:
                rule = self._rule(rules, rate_plan.id, target)
                rule.selling_rate = _rate_for_day(payload, target)
                updated += 1
        await self.db.commit()
        return BulkOperationResult(updated=updated)

    async def update_status(
        self, payload: BulkRoomStatusUpdate, user: User
    ) -> BulkOperationResult:
        rate_plans = await self._rate_plans(
            payload.sanatorium_id, payload.rate_plan_ids
        )
        await assert_sanatorium_access(
            self.db, payload.sanatorium_id, user, action="bulk open or close rooms"
        )
        dates = _scope_dates(payload.date_ranges, payload.weekdays)
        rules = await self._rules([rp.id for rp in rate_plans], dates)
        updated = 0
        for rate_plan in rate_plans:
            for target in dates:
                self._rule(rules, rate_plan.id, target).is_closed = payload.is_closed
                updated += 1
        await self.db.commit()
        return BulkOperationResult(updated=updated)

    async def update_restrictions(
        self, payload: BulkRestrictionsUpdate, user: User
    ) -> BulkOperationResult:
        rate_plans = await self._rate_plans(
            payload.sanatorium_id, payload.rate_plan_ids
        )
        await assert_sanatorium_access(
            self.db, payload.sanatorium_id, user, action="bulk edit restrictions"
        )
        dates = _scope_dates(payload.date_ranges, payload.weekdays)
        rules = await self._rules([rp.id for rp in rate_plans], dates)
        updates = payload.model_dump(exclude_unset=True)
        for key in (
            "sanatorium_id",
            "date_ranges",
            "weekdays",
            "rate_plan_ids",
            "clear",
        ):
            updates.pop(key, None)
        updated = 0
        for rate_plan in rate_plans:
            for target in dates:
                rule = self._rule(rules, rate_plan.id, target)
                for field, value in updates.items():
                    setattr(rule, field, value)
                for field in payload.clear:
                    setattr(rule, field.value, None)
                updated += 1
        await self.db.commit()
        return BulkOperationResult(updated=updated)

    async def copy_rates(
        self, payload: BulkCopyRates, user: User
    ) -> BulkOperationResult:
        rate_plans = await self._rate_plans(
            payload.sanatorium_id, payload.rate_plan_ids
        )
        await assert_sanatorium_access(
            self.db, payload.sanatorium_id, user, action="copy rates"
        )
        source_dates = _filtered_range(
            payload.source_date_from, payload.source_date_to, payload.weekdays
        )
        target_dates = _filtered_range(
            payload.target_date_from, payload.target_date_to, payload.weekdays
        )
        source_rules = await self._rules([rp.id for rp in rate_plans], source_dates)
        target_rules = await self._rules([rp.id for rp in rate_plans], target_dates)
        updated = 0
        for rate_plan in rate_plans:
            for target in target_dates:
                target_rule = self._rule(target_rules, rate_plan.id, target)
                if (
                    target_rule.selling_rate is not None
                    and not payload.overwrite_existing
                ):
                    continue
                source = _source_date(
                    payload.alignment, source_dates, target_dates, target
                )
                source_rule = source_rules.get((rate_plan.id, source))
                price = (
                    source_rule.selling_rate
                    if source_rule and source_rule.selling_rate is not None
                    else calculate_rate_plan_night_price(
                        rate_plan.room, rate_plan, source, rate_plan.room.price_periods
                    )
                )
                target_rule.selling_rate = _adjust(
                    price, payload.adjustment, payload.adjustment_percent
                )
                updated += 1
        await self.db.commit()
        return BulkOperationResult(updated=updated)

    async def _rate_plans(
        self, sanatorium_id: uuid.UUID, rate_plan_ids: list[uuid.UUID]
    ) -> list[RatePlan]:
        rows = list(
            (
                await self.db.scalars(
                    select(RatePlan)
                    .join(Room, RatePlan.room_id == Room.id)
                    .where(
                        Room.sanatorium_id == sanatorium_id,
                        RatePlan.id.in_(rate_plan_ids),
                    )
                    .options(
                        selectinload(RatePlan.room).selectinload(Room.price_periods)
                    )
                )
            ).all()
        )
        if len({row.id for row in rows}) != len(set(rate_plan_ids)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="rate_plan_ids must belong to the selected sanatorium",
            )
        return rows

    async def _rules(
        self, rate_plan_ids: list[uuid.UUID], dates: list[date]
    ) -> dict[tuple[uuid.UUID, date], RatePlanDateRule]:
        rows = list(
            (
                await self.db.scalars(
                    select(RatePlanDateRule)
                    .where(
                        RatePlanDateRule.rate_plan_id.in_(rate_plan_ids),
                        RatePlanDateRule.date.in_(dates),
                    )
                    .with_for_update()
                )
            ).all()
        )
        return {(row.rate_plan_id, row.date): row for row in rows}

    async def _availability(
        self, room_id: uuid.UUID, dates: list[date]
    ) -> dict[date, RoomAvailability]:
        rows = await self.db.scalars(
            select(RoomAvailability)
            .where(
                RoomAvailability.room_id == room_id,
                RoomAvailability.date.in_(dates),
            )
            .with_for_update()
        )
        return {row.date: row for row in rows}

    def _rule(
        self,
        rules: dict[tuple[uuid.UUID, date], RatePlanDateRule],
        rate_plan_id: uuid.UUID,
        target: date,
    ) -> RatePlanDateRule:
        key = (rate_plan_id, target)
        rule = rules.get(key)
        if rule is None:
            rule = RatePlanDateRule(rate_plan_id=rate_plan_id, date=target)
            self.db.add(rule)
            rules[key] = rule
        return rule

    def _set_availability(
        self,
        row: RoomAvailability | None,
        room: Room,
        target: date,
        units_blocked: int,
    ) -> None:
        if row is None:
            self.db.add(
                RoomAvailability(
                    room_id=room.id,
                    date=target,
                    units_blocked=units_blocked,
                    units_booked=0,
                )
            )
        else:
            row.units_blocked = units_blocked


def _scope_dates(date_ranges, weekdays: list[int]) -> list[date]:
    dates: set[date] = set()
    for item in date_ranges:
        dates.update(_filtered_range(item.date_from, item.date_to, weekdays))
    return sorted(dates)


def _filtered_range(start: date, end: date, weekdays: list[int]) -> list[date]:
    return [
        d for d in date_range(start, end + timedelta(days=1)) if d.weekday() in weekdays
    ]


def _rate_for_day(payload: BulkRatesUpdate, target: date) -> Decimal:
    if payload.weekend_selling_rate is not None and target.weekday() in {4, 5}:
        return payload.weekend_selling_rate
    return payload.selling_rate


def _source_date(
    alignment: CopyRateAlignment,
    source_dates: list[date],
    target_dates: list[date],
    target: date,
) -> date:
    if not source_dates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="source date range has no dates after weekday filtering",
        )
    if alignment == CopyRateAlignment.DAY_OF_WEEK:
        matches = [d for d in source_dates if d.weekday() == target.weekday()]
        return matches[0] if matches else source_dates[0]
    index = target_dates.index(target)
    if alignment == CopyRateAlignment.CUSTOM_RANGE:
        return source_dates[index % len(source_dates)]
    return source_dates[min(index, len(source_dates) - 1)]


def _adjust(
    price: Decimal, adjustment: CopyRateAdjustment, percent: Decimal | None
) -> Decimal:
    if adjustment == CopyRateAdjustment.INCREASE_PERCENT:
        price *= 1 + (percent or Decimal("0")) / 100
    elif adjustment == CopyRateAdjustment.DECREASE_PERCENT:
        price *= 1 - (percent or Decimal("0")) / 100
    return price.quantize(Decimal("0.01"), ROUND_HALF_UP)


def get_bulk_availability_service(
    db: AsyncSession = Depends(get_db),
) -> BulkAvailabilityService:
    return BulkAvailabilityService(db)
