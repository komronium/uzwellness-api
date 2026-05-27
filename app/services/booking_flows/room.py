from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.pricing import (
    calculate_stay_total,
    convert_to_usd,
    convert_to_uzs,
)
from app.core.utils import date_range, pick_locale
from app.models.booking import Booking, BookingStatus, BookingType
from app.models.exchange_rate import ExchangeRate
from app.models.extra_bed import BookingExtraBed, ExtraBedConfig
from app.models.notification import Notification
from app.models.rate_plan import RatePlan
from app.models.room import Room
from app.models.user import User, UserRole
from app.schemas.booking import BookingCreate
from app.services.booking_flows.base import BookingFlowBase, rooms_count_for_guests
from app.services.exchange_rate_service import USD_UZS

_CENTS = Decimal("0.01")
_UNFETCHED: object = object()


class RoomBookingFlow(BookingFlowBase):
    booking_type = BookingType.ROOM

    def matches(self, payload: BookingCreate) -> bool:
        return (
            payload.program_id is None
            and payload.package_id is None
            and payload.room_id is not None
        )

    async def create(self, payload: BookingCreate, user: User) -> Booking:
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

        await self._reserve_units(room, all_dates, rooms_count)

        is_b2b = user.role == UserRole.AGENT
        rooms_total = calculate_stay_total(
            room, all_dates, room.price_periods
        ) * rooms_count
        board_total = Decimal("0")
        promo_percent = Decimal("0")
        if rate_plan is not None:
            if rate_plan.price_adjustment_percent is not None:
                rooms_total *= 1 + rate_plan.price_adjustment_percent / 100
            if rate_plan.board_optional and rate_plan.board_price is not None:
                board_total = rate_plan.board_price * payload.guests * nights
            promo_percent = self._active_promo_percent(rate_plan)
        extra_bed_records = await self._build_extra_beds(
            payload, room.sanatorium_id, nights, room.base_currency
        )
        extras_total = sum(
            (eb.total_price for eb in extra_bed_records), Decimal("0")
        )
        room_and_board = rooms_total + board_total
        original_price: Decimal | None = None
        if promo_percent > 0:
            original_price = (room_and_board + extras_total).quantize(
                _CENTS, ROUND_HALF_UP
            )
            room_and_board *= 1 - promo_percent / 100
        base_total = (room_and_board + extras_total).quantize(_CENTS, ROUND_HALF_UP)

        pricing = await self.pricing.apply(
            base_total=base_total,
            sanatorium=sanatorium,
            user=user,
            is_b2b=is_b2b,
        )

        booking = Booking(
            user_id=user.id,
            room_id=room.id,
            rate_plan_id=rate_plan.id if rate_plan is not None else None,
            booking_type=BookingType.ROOM,
            check_in=payload.check_in,
            check_out=payload.check_out,
            guests=payload.guests,
            rooms_count=rooms_count,
            status=BookingStatus.CONFIRMED,
            final_price=pricing.final_price,
            original_price=original_price,
            promo_percent_snapshot=promo_percent if promo_percent > 0 else None,
            currency=room.base_currency,
            is_b2b=is_b2b,
            guest_details=[g.model_dump() for g in payload.guest_details],
            commission_snapshot=pricing.commission_amount,
            commission_percent_snapshot=pricing.commission_percent,
            agent_discount_percent_snapshot=(
                pricing.agent_discount_percent if is_b2b else None
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
                rate_plan.cancellation_penalty_amount
                if rate_plan is not None
                else None
            ),
            payment_timing=(
                rate_plan.payment_timing if rate_plan is not None else None
            ),
        )
        self.db.add(booking)
        await self.db.flush()
        for eb in extra_bed_records:
            eb.booking_id = booking.id
            self.db.add(eb)
        self.db.add(
            Notification(
                booking_id=booking.id, type="booking_created", channel="email"
            )
        )
        await self.db.commit()

        self._send_received_email(booking, user, pick_locale(sanatorium.name))
        return await self._load(booking.id)

    async def _lock_room(self, room_id) -> Room:
        room = await self.db.scalar(
            select(Room)
            .where(Room.id == room_id)
            .options(selectinload(Room.price_periods))
            .with_for_update(of=Room)
        )
        if room is None or not room.is_active:
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
        if (
            rate_plan is None
            or not rate_plan.is_active
            or rate_plan.room_id != room.id
        ):
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
        config_ids = [item.config_id for item in payload.extra_beds]
        configs = {}
        if config_ids:
            configs = {
                config.id: config
                for config in (
                    await self.db.scalars(
                        select(ExtraBedConfig).where(ExtraBedConfig.id.in_(config_ids))
                    )
                ).all()
            }
        for item in payload.extra_beds:
            config = configs.get(item.config_id)
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

            if config.currency == room_currency:
                price_per_night = config.price_per_night
            else:
                if rate is _UNFETCHED:
                    rate = await self.db.scalar(
                        select(ExchangeRate).where(ExchangeRate.pair == USD_UZS)
                    )
                converter = (
                    convert_to_usd if room_currency == "USD" else convert_to_uzs
                )
                converted = converter(
                    config.price_per_night, config.currency, rate  # type: ignore[arg-type]
                )
                if converted is None:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            "Exchange rate is not configured; cannot convert extra "
                            f"bed from {config.currency} to {room_currency}"
                        ),
                    )
                price_per_night = converted

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
