from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.utils import date_range, today_tashkent
from app.models.availability import RoomAvailability
from app.models.booking import Booking, BookingStatus, BookingType
from app.models.notification import Notification
from app.models.rate_plan import RatePlan
from app.models.room import Room
from app.models.sanatorium import Sanatorium, SanatoriumStatus
from app.models.user import User, UserRole
from app.schemas.booking import RoomOfferBookingCreate
from app.schemas.room_offer import RoomOfferSearchRequest
from app.services.booking_pricing_policy import (
    BookingPricingPolicy,
    get_booking_pricing_policy,
)
from app.services.room_offer_service import RoomOfferService, get_room_offer_service


class RoomOfferBookingService:
    def __init__(
        self,
        db: AsyncSession,
        offers: RoomOfferService,
        pricing: BookingPricingPolicy,
    ) -> None:
        self.db = db
        self.offers = offers
        self.pricing = pricing

    async def create(
        self, payload: RoomOfferBookingCreate, user: User, *, locale: str
    ) -> Booking:
        if payload.check_in < today_tashkent():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="check_in must be today or in the future",
            )
        sanatorium = await self._approved_sanatorium(payload.sanatorium_id)
        response = await self.offers.search(
            sanatorium_id=payload.sanatorium_id,
            payload=RoomOfferSearchRequest(
                check_in=payload.check_in,
                check_out=payload.check_out,
                rooms=payload.rooms,
                guest_options=payload.guest_options,
                treatment_selections=payload.treatment_selections,
            ),
            locale=locale,
        )
        self._assert_treatment_selections_applied(payload, response)
        offer = next(
            (
                item
                for item in response.offers
                if item.room_id == payload.room_id
                and item.rate_plan_id == payload.rate_plan_id
            ),
            None,
        )
        if offer is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Selected room offer is no longer available",
            )

        room = await self._lock_room(payload.room_id)
        await self._reserve_units(
            room,
            dates=list(date_range(payload.check_in, payload.check_out)),
            rooms_count=len(payload.rooms),
        )
        rate_plan = await self._rate_plan(payload.rate_plan_id)
        is_b2b = user.role == UserRole.AGENT
        pricing = await self.pricing.apply(
            base_total=offer.price.total,
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
            adults=payload.adults,
            children=payload.children,
            rooms_count=len(payload.rooms),
            status=BookingStatus.CONFIRMED,
            final_price=pricing.final_price,
            original_price=offer.price.original_total,
            currency=offer.price.currency,
            is_b2b=is_b2b,
            guest_details=[guest.model_dump() for guest in payload.guest_details],
            room_distribution=[
                room_request.model_dump(mode="json") for room_request in payload.rooms
            ],
            guest_options=[
                option.model_dump(mode="json") for option in payload.guest_options
            ],
            treatment_selections=[
                selection.model_dump(mode="json")
                for selection in payload.treatment_selections
            ],
            offer_snapshot=offer.model_dump(mode="json"),
            special_requests=payload.special_requests,
            commission_snapshot=pricing.commission_amount,
            commission_percent_snapshot=pricing.commission_percent,
            agent_discount_percent_snapshot=(
                pricing.agent_discount_percent if is_b2b else None
            ),
            board=rate_plan.board if rate_plan is not None else None,
            refundable=rate_plan.refundable if rate_plan is not None else None,
            free_cancellation_days=rate_plan.free_cancellation_days
            if rate_plan is not None
            else None,
            cancellation_penalty_percent=rate_plan.cancellation_penalty_percent
            if rate_plan is not None
            else None,
            cancellation_penalty_amount=rate_plan.cancellation_penalty_amount
            if rate_plan is not None
            else None,
            payment_timing=rate_plan.payment_timing if rate_plan is not None else None,
            confirmation=rate_plan.confirmation if rate_plan is not None else None,
            rate_plan_name=rate_plan.name if rate_plan is not None else None,
            board_guests=rate_plan.board_guests if rate_plan is not None else None,
        )
        self.db.add(booking)
        await self.db.flush()
        self.db.add(
            Notification(booking_id=booking.id, type="booking_created", channel="email")
        )
        await self.db.commit()
        return await self._load_required(booking.id)

    async def _approved_sanatorium(self, sanatorium_id: uuid.UUID) -> Sanatorium:
        sanatorium = await self.db.get(Sanatorium, sanatorium_id)
        if sanatorium is None or sanatorium.status != SanatoriumStatus.APPROVED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Sanatorium is not available for booking",
            )
        return sanatorium

    async def _lock_room(self, room_id: uuid.UUID) -> Room:
        room = await self.db.scalar(
            select(Room).where(Room.id == room_id).with_for_update(of=Room)
        )
        if room is None or not room.is_active or room.deleted_at is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Selected room is no longer available",
            )
        return room

    async def _rate_plan(self, rate_plan_id: uuid.UUID | None) -> RatePlan | None:
        if rate_plan_id is None:
            return None
        rate_plan = await self.db.get(RatePlan, rate_plan_id)
        if rate_plan is None or not rate_plan.is_active:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Selected rate plan is no longer available",
            )
        return rate_plan

    @staticmethod
    def _assert_treatment_selections_applied(
        payload: RoomOfferBookingCreate, response
    ) -> None:
        selected = {
            (item.room_index, item.guest.guest_index): item.selected_program_id
            for item in response.treatment_selection
        }
        for item in payload.treatment_selections:
            if selected.get((item.room_index, item.guest_index)) != item.program_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Treatment selection is not available for this guest",
                )

    async def _reserve_units(
        self, room: Room, *, dates: list, rooms_count: int
    ) -> None:
        existing = {
            row.date: row
            for row in await self.db.scalars(
                select(RoomAvailability)
                .where(
                    RoomAvailability.room_id == room.id,
                    RoomAvailability.date.in_(dates),
                )
                .with_for_update()
            )
        }
        for target in dates:
            row = existing.get(target)
            if row is None:
                self.db.add(
                    RoomAvailability(
                        room_id=room.id,
                        date=target,
                        units_blocked=0,
                        units_booked=rooms_count,
                    )
                )
                continue
            if (
                row.units_blocked + row.units_booked + rooms_count
                > room.inventory_count
            ):
                free = room.inventory_count - row.units_blocked - row.units_booked
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Only {max(free, 0)} unit(s) free on {target}, "
                        f"need {rooms_count}"
                    ),
                )
            row.units_booked += rooms_count

    async def _load_required(self, booking_id: uuid.UUID) -> Booking:
        booking = await self.db.scalar(
            select(Booking)
            .options(
                selectinload(Booking.extra_beds),
                selectinload(Booking.user),
                selectinload(Booking.payments),
            )
            .where(Booking.id == booking_id)
        )
        if booking is None:
            raise RuntimeError(f"Booking {booking_id} not found after write")
        return booking


def get_room_offer_booking_service(
    db: AsyncSession = Depends(get_db),
    offers: RoomOfferService = Depends(get_room_offer_service),
    pricing: BookingPricingPolicy = Depends(get_booking_pricing_policy),
) -> RoomOfferBookingService:
    return RoomOfferBookingService(db, offers, pricing)
