from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.pricing import (
    calculate_rate_plan_night_price,
    calculate_stay_total,
    convert_to_usd,
    convert_to_uzs,
)
from app.core.utils import date_range, pick_locale
from app.models.booking import Booking, BookingStatus, BookingType
from app.models.exchange_rate import ExchangeRate
from app.models.extra_bed import BookingExtraBed, ExtraBedConfig
from app.models.rate_plan import RatePlan, RatePlanDateRule
from app.models.room import Room
from app.models.sanatorium import Sanatorium
from app.models.user import User, UserRole
from app.schemas.booking import BookingCreate
from app.services.booking_flows.base import BookingFlowBase, rooms_count_for_guests
from app.services.booking_pricing_policy import BookingPricing
from app.services.exchange_rate_service import USD_UZS

_CENTS = Decimal("0.01")
_UNFETCHED: object = object()


@dataclass(slots=True)
class RoomBookingContext:
    nights: int
    dates: list
    room: Room
    sanatorium: Sanatorium
    rooms_count: int
    rate_plan: RatePlan | None
    rate_rules: dict
    is_b2b: bool


@dataclass(slots=True)
class RoomBookingQuote:
    pricing: BookingPricing
    original_price: Decimal | None
    promo_percent: Decimal
    extra_beds: list[BookingExtraBed]


class RoomBookingFlow(BookingFlowBase):
    booking_type = BookingType.ROOM

    def matches(self, payload: BookingCreate) -> bool:
        return (
            payload.program_id is None
            and payload.package_id is None
            and payload.room_id is not None
        )

    async def create(self, payload: BookingCreate, user: User) -> Booking:
        context = await self._prepare_context(payload, user)
        await self._reserve_units(context.room, context.dates, context.rooms_count)

        quote = await self._quote(payload, user, context)
        booking = self._build_booking(payload, user, context, quote)
        self.db.add(booking)
        await self.db.flush()
        self._attach_extra_beds(booking, quote.extra_beds)
        self.db.add(self._queue_created_notification(booking))
        await self.db.commit()
        self._send_received_email(booking, user, pick_locale(context.sanatorium.name))
        return await self._load(booking.id)

    async def _prepare_context(
        self, payload: BookingCreate, user: User
    ) -> RoomBookingContext:
        if payload.check_out is None or payload.check_out <= payload.check_in:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="check_out must be after check_in",
            )

        nights = (payload.check_out - payload.check_in).days
        all_dates = list(date_range(payload.check_in, payload.check_out))

        room = await self._lock_room(payload.room_id)
        sanatorium = await self._approved_sanatorium(room.sanatorium_id)
        rooms_count = self._validate_and_compute_rooms(room, payload, nights)
        rate_plan = await self._load_rate_plan(payload.rate_plan_id, room, nights)
        rate_rules = await self._load_rate_rules(rate_plan, all_dates)
        self._assert_rate_rules(rate_rules, all_dates, nights)
        return RoomBookingContext(
            nights=nights,
            dates=all_dates,
            room=room,
            sanatorium=sanatorium,
            rooms_count=rooms_count,
            rate_plan=rate_plan,
            rate_rules=rate_rules,
            is_b2b=user.role == UserRole.AGENT,
        )

    async def _quote(
        self, payload: BookingCreate, user: User, context: RoomBookingContext
    ) -> RoomBookingQuote:
        room_and_board, promo_percent = self._room_and_board_total(payload, context)
        extra_bed_records = await self._build_extra_beds(
            payload,
            context.room.sanatorium_id,
            context.nights,
            context.room.base_currency,
        )
        extras_total = sum((eb.total_price for eb in extra_bed_records), Decimal("0"))
        original_price: Decimal | None = None
        if promo_percent > 0:
            original_price = (room_and_board + extras_total).quantize(
                _CENTS, ROUND_HALF_UP
            )
            room_and_board *= 1 - promo_percent / 100
        base_total = (room_and_board + extras_total).quantize(_CENTS, ROUND_HALF_UP)

        pricing = await self.pricing.apply(
            base_total=base_total,
            sanatorium=context.sanatorium,
            user=user,
            is_b2b=context.is_b2b,
        )
        return RoomBookingQuote(
            pricing=pricing,
            original_price=original_price,
            promo_percent=promo_percent,
            extra_beds=extra_bed_records,
        )

    def _room_and_board_total(
        self, payload: BookingCreate, context: RoomBookingContext
    ) -> tuple[Decimal, Decimal]:
        rate_plan = context.rate_plan
        rooms_total = self._rooms_total(context)
        board_total = Decimal("0")
        promo_percent = Decimal("0")
        if rate_plan is not None:
            if rate_plan.board_optional and rate_plan.board_price is not None:
                board_total = rate_plan.board_price * payload.guests * context.nights
            promo_percent = self._active_promo_percent(rate_plan)
        return rooms_total + board_total, promo_percent

    def _rooms_total(self, context: RoomBookingContext) -> Decimal:
        room = context.room
        rate_plan = context.rate_plan
        if rate_plan is None:
            return (
                calculate_stay_total(room, context.dates, room.price_periods)
                * context.rooms_count
            )
        total = Decimal("0")
        for target in context.dates:
            rule = context.rate_rules.get(target)
            total += (
                calculate_rate_plan_night_price(
                    room,
                    rate_plan,
                    target,
                    room.price_periods,
                    selling_rate_override=rule.selling_rate if rule else None,
                )
                * context.rooms_count
            )
        return total

    def _build_booking(
        self,
        payload: BookingCreate,
        user: User,
        context: RoomBookingContext,
        quote: RoomBookingQuote,
    ) -> Booking:
        rate_plan = context.rate_plan
        pricing = quote.pricing
        return Booking(
            user_id=user.id,
            room_id=context.room.id,
            rate_plan_id=rate_plan.id if rate_plan is not None else None,
            booking_type=BookingType.ROOM,
            check_in=payload.check_in,
            check_out=payload.check_out,
            guests=payload.guests,
            rooms_count=context.rooms_count,
            status=BookingStatus.CONFIRMED,
            final_price=pricing.final_price,
            original_price=quote.original_price,
            promo_percent_snapshot=(
                quote.promo_percent if quote.promo_percent > 0 else None
            ),
            currency=context.room.base_currency,
            is_b2b=context.is_b2b,
            guest_details=[g.model_dump() for g in payload.guest_details],
            special_requests=payload.special_requests,
            commission_snapshot=pricing.commission_amount,
            commission_percent_snapshot=pricing.commission_percent,
            agent_discount_percent_snapshot=(
                pricing.agent_discount_percent if context.is_b2b else None
            ),
            board=rate_plan.board if rate_plan is not None else None,
            refundable=rate_plan.refundable if rate_plan is not None else None,
            free_cancellation_days=(
                rate_plan.free_cancellation_days if rate_plan is not None else None
            ),
            cancellation_penalty_percent=(
                rate_plan.cancellation_penalty_percent
                if rate_plan is not None
                else None
            ),
            cancellation_penalty_amount=(
                rate_plan.cancellation_penalty_amount if rate_plan is not None else None
            ),
            payment_timing=(
                rate_plan.payment_timing if rate_plan is not None else None
            ),
            confirmation=rate_plan.confirmation if rate_plan is not None else None,
            rate_plan_name=rate_plan.name if rate_plan is not None else None,
            board_guests=rate_plan.board_guests if rate_plan is not None else None,
        )

    def _attach_extra_beds(
        self, booking: Booking, records: list[BookingExtraBed]
    ) -> None:
        for eb in records:
            eb.booking_id = booking.id
            self.db.add(eb)

    async def _lock_room(self, room_id) -> Room:
        room = await self.db.scalar(
            select(Room)
            .where(Room.id == room_id)
            .options(selectinload(Room.price_periods))
            .with_for_update(of=Room)
        )
        if room is None or not room.is_active or room.deleted_at is not None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Room not found"
            )
        return room

    async def _load_rate_plan(
        self, rate_plan_id, room: Room, nights: int
    ) -> RatePlan | None:
        if rate_plan_id is None:
            return None
        rate_plan = await self.db.get(RatePlan, rate_plan_id)
        if rate_plan is None or not rate_plan.is_active or rate_plan.room_id != room.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Rate plan not found for this room",
            )
        if rate_plan.min_nights is not None and nights < rate_plan.min_nights:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"This rate requires at least {rate_plan.min_nights} night(s)",
            )
        if rate_plan.max_nights is not None and nights > rate_plan.max_nights:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"This rate allows at most {rate_plan.max_nights} night(s)",
            )
        return rate_plan

    async def _load_rate_rules(self, rate_plan: RatePlan | None, dates: list) -> dict:
        if rate_plan is None:
            return {}
        rows = (
            await self.db.scalars(
                select(RatePlanDateRule).where(
                    RatePlanDateRule.rate_plan_id == rate_plan.id,
                    RatePlanDateRule.date.in_(dates),
                )
            )
        ).all()
        return {row.date: row for row in rows}

    @staticmethod
    def _assert_rate_rules(rules: dict, dates: list, nights: int) -> None:
        arrival_rule = rules.get(dates[0]) if dates else None
        now = datetime.now(timezone.utc)
        for target in dates:
            rule = rules.get(target)
            if rule is None:
                continue
            if rule.is_closed is True:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Rate plan is closed on {target}",
                )
            if rule.min_stay_nights is not None and nights < rule.min_stay_nights:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Minimum stay is {rule.min_stay_nights} night(s)",
                )
        if arrival_rule is None:
            return
        hours_until_arrival = (
            datetime.combine(dates[0], datetime.min.time(), tzinfo=timezone.utc) - now
        ).total_seconds() / 3600
        if (
            arrival_rule.min_advance_hours is not None
            and hours_until_arrival < arrival_rule.min_advance_hours
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Booking is too close to arrival for this rate plan",
            )
        if (
            arrival_rule.max_advance_hours is not None
            and hours_until_arrival > arrival_rule.max_advance_hours
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Booking is too far in advance for this rate plan",
            )
        if (
            arrival_rule.min_stay_arrival_nights is not None
            and nights < arrival_rule.min_stay_arrival_nights
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Minimum length of stay from arrival is "
                    f"{arrival_rule.min_stay_arrival_nights} night(s)"
                ),
            )

    @staticmethod
    def _active_promo_percent(rate_plan: RatePlan) -> Decimal:
        if rate_plan.promo_percent is None:
            return Decimal("0")
        now = datetime.now(UTC)
        if rate_plan.promo_starts_at is not None and now < rate_plan.promo_starts_at:
            return Decimal("0")
        if rate_plan.promo_ends_at is not None and now > rate_plan.promo_ends_at:
            return Decimal("0")
        return rate_plan.promo_percent

    @staticmethod
    def _validate_and_compute_rooms(
        room: Room, payload: BookingCreate, nights: int
    ) -> int:
        if nights < room.min_nights:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Minimum stay is {room.min_nights} night(s)",
            )
        return rooms_count_for_guests(room, payload.guests)

    async def _build_extra_beds(
        self,
        payload: BookingCreate,
        sanatorium_id,
        nights: int,
        room_currency: str,
    ) -> list[BookingExtraBed]:
        records: list[BookingExtraBed] = []
        rate: ExchangeRate | None | object = _UNFETCHED
        configs = await self._load_extra_bed_configs(payload)
        for item in payload.extra_beds:
            config = configs.get(item.config_id)
            self._assert_extra_bed_config(config, item, sanatorium_id)
            price_per_night, rate = await self._extra_bed_price(
                config, room_currency, rate
            )

            total = (price_per_night * item.count * nights).quantize(
                _CENTS, ROUND_HALF_UP
            )
            records.append(
                BookingExtraBed(
                    config_id=config.id,
                    name_snapshot=config.name,
                    price_per_night_snapshot=price_per_night,
                    currency=room_currency,
                    count=item.count,
                    total_price=total,
                )
            )
        return records

    async def _load_extra_bed_configs(self, payload: BookingCreate) -> dict:
        config_ids = [item.config_id for item in payload.extra_beds]
        if not config_ids:
            return {}
        configs = await self.db.scalars(
            select(ExtraBedConfig).where(ExtraBedConfig.id.in_(config_ids))
        )
        return {config.id: config for config in configs.all()}

    @staticmethod
    def _assert_extra_bed_config(config, item, sanatorium_id) -> None:
        if config is None or not config.is_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Extra bed config {item.config_id} not found",
            )
        if config.sanatorium_id != sanatorium_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Extra bed config does not belong to this sanatorium",
            )
        if item.count > config.max_count:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Maximum {config.max_count} of this bed type allowed",
            )

    async def _extra_bed_price(
        self,
        config: ExtraBedConfig,
        room_currency: str,
        rate: ExchangeRate | None | object,
    ) -> tuple[Decimal, ExchangeRate | None | object]:
        if config.currency == room_currency:
            return config.price_per_night, rate
        if rate is _UNFETCHED:
            rate = await self.db.scalar(
                select(ExchangeRate).where(ExchangeRate.pair == USD_UZS)
            )
        if rate is not None and not isinstance(rate, ExchangeRate):
            raise RuntimeError("Unexpected exchange rate sentinel")
        converter = convert_to_usd if room_currency == "USD" else convert_to_uzs
        converted = converter(config.price_per_night, config.currency, rate)
        if converted is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Exchange rate is not configured; cannot convert extra "
                    f"bed from {config.currency} to {room_currency}"
                ),
            )
        return converted, rate
