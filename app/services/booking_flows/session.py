from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException, status

from app.core.utils import pick_locale
from app.models.booking import Booking, BookingStatus, BookingType
from app.models.notification import Notification
from app.models.program import TreatmentProgram
from app.models.user import User, UserRole
from app.schemas.booking import BookingCreate
from app.services.booking_flows.base import BookingFlowBase

_CENTS = Decimal("0.01")


class SessionBookingFlow(BookingFlowBase):
    booking_type = BookingType.SESSION

    def matches(self, payload: BookingCreate) -> bool:
        return payload.program_id is not None

    async def create(self, payload: BookingCreate, user: User) -> Booking:
        program = await self.db.get(TreatmentProgram, payload.program_id)
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
        self._send_received_email(booking, user, pick_locale(sanatorium.name))
        return await self._load(booking.id)
