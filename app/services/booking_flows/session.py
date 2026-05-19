from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.notifier import BookingNotifier
from app.models.booking import Booking, BookingStatus, BookingType
from app.models.notification import Notification
from app.models.program import TreatmentProgram
from app.models.sanatorium import Sanatorium, SanatoriumStatus
from app.models.user import User, UserRole
from app.schemas.booking import BookingCreate
from app.services.booking_pricing_policy import BookingPricingPolicy
from app.services.email_service import BookingEmailContext

_CENTS = Decimal("0.01")


class SessionBookingFlow:
    booking_type = BookingType.SESSION

    def __init__(
        self,
        db: AsyncSession,
        pricing: BookingPricingPolicy,
        notifier: BookingNotifier,
    ) -> None:
        self.db = db
        self.pricing = pricing
        self.notifier = notifier

    def matches(self, payload: BookingCreate) -> bool:
        return payload.program_id is not None

    async def create(self, payload: BookingCreate, user: User) -> Booking:
        program = (
            await self.db.execute(
                select(TreatmentProgram).where(
                    TreatmentProgram.id == payload.program_id
                )
            )
        ).scalar_one_or_none()
        if program is None or not program.is_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Program not found"
            )
        if program.price is None or program.currency is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Program is not bookable (no price set)",
            )
        sanatorium = await self._approved_sanatorium(program.sanatorium_id)

        if (
            program.group_size_max is not None
            and payload.guests > program.group_size_max
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Maximum {program.group_size_max} participant(s) per session",
            )

        check_out = payload.check_out or payload.check_in
        if check_out < payload.check_in:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="check_out must be on or after check_in",
            )

        is_b2b = user.role == UserRole.AGENT
        base_total = (program.price * payload.guests).quantize(
            _CENTS, ROUND_HALF_UP
        )
        pricing = await self.pricing.apply(
            base_total=base_total,
            sanatorium=sanatorium,
            user=user,
            is_b2b=is_b2b,
            payload=payload,
        )
        booking = Booking(
            user_id=user.id,
            program_id=program.id,
            booking_type=BookingType.SESSION,
            check_in=payload.check_in,
            check_out=check_out,
            guests=payload.guests,
            status=BookingStatus.CONFIRMED,
            final_price=pricing.final_price,
            currency=program.currency,
            is_b2b=is_b2b,
            b2b_client_price=pricing.b2b_client_price,
            guest_details=[g.model_dump() for g in payload.guest_details],
            commission_snapshot=pricing.commission_amount,
            commission_percent_snapshot=pricing.commission_percent,
            agent_discount_percent_snapshot=(
                pricing.agent_discount_percent if is_b2b else None
            ),
        )
        self.db.add(booking)
        await self.db.flush()
        self.db.add(
            Notification(
                booking_id=booking.id, type="booking_created", channel="email"
            )
        )
        await self.db.commit()
        await self._send_received_email(booking, user, sanatorium.name)
        return await self._load(booking.id)

    async def _approved_sanatorium(self, sanatorium_id) -> Sanatorium:
        sanatorium = (
            await self.db.execute(
                select(Sanatorium).where(Sanatorium.id == sanatorium_id)
            )
        ).scalar_one_or_none()
        if sanatorium is None or sanatorium.status != SanatoriumStatus.APPROVED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Sanatorium is not available for booking",
            )
        return sanatorium

    async def _load(self, booking_id) -> Booking:
        stmt = (
            select(Booking)
            .options(selectinload(Booking.extra_beds), selectinload(Booking.user))
            .where(Booking.id == booking_id)
        )
        return (await self.db.execute(stmt)).scalar_one()

    async def _send_received_email(
        self, booking: Booking, user: User, sanatorium_name: str
    ) -> None:
        if not user.email:
            return
        ctx = BookingEmailContext(
            booking_code=booking.code,
            sanatorium_name=sanatorium_name,
            check_in=booking.check_in,
            check_out=booking.check_out,
            guest_name=user.full_name or user.email,
            total_price=booking.final_price,
            currency=booking.currency,
        )
        self.notifier.booking_received(to=user.email, ctx=ctx)
