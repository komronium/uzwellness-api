from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException, status

from app.core.utils import pick_locale
from app.models.booking import Booking, BookingStatus, BookingType
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
        program = await self._load_bookable_program(payload.program_id)
        self._assert_group_size(program, payload.guests)
        check_out = self._check_out(payload)
        sanatorium = await self._approved_sanatorium(program.sanatorium_id)
        is_b2b = user.role == UserRole.AGENT
        base_total = self._base_total(program, payload.guests)
        pricing = await self.pricing.apply(
            base_total=base_total,
            sanatorium=sanatorium,
            user=user,
            is_b2b=is_b2b,
        )
        booking = self._build_booking(
            payload,
            user=user,
            program=program,
            check_out=check_out,
            pricing=pricing,
            is_b2b=is_b2b,
        )
        self.db.add(booking)
        await self.db.flush()
        self.db.add(self._queue_created_notification(booking))
        await self.db.commit()
        self._send_received_email(booking, user, pick_locale(sanatorium.name))
        return await self._load(booking.id)

    async def _load_bookable_program(self, program_id) -> TreatmentProgram:
        program = await self.db.get(TreatmentProgram, program_id)
        if program is None or not program.is_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Program not found"
            )
        if program.price is None or program.currency is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Program is not bookable (no price set)",
            )
        return program

    @staticmethod
    def _assert_group_size(program: TreatmentProgram, guests: int) -> None:
        if program.group_size_max is not None and guests > program.group_size_max:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Maximum {program.group_size_max} participant(s) per session",
            )

    @staticmethod
    def _check_out(payload: BookingCreate):
        check_out = payload.check_out or payload.check_in
        if check_out < payload.check_in:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="check_out must be on or after check_in",
            )
        return check_out

    @staticmethod
    def _base_total(program: TreatmentProgram, guests: int) -> Decimal:
        return (program.price * guests).quantize(_CENTS, ROUND_HALF_UP)

    @staticmethod
    def _build_booking(
        payload: BookingCreate,
        *,
        user: User,
        program: TreatmentProgram,
        check_out,
        pricing,
        is_b2b: bool,
    ) -> Booking:
        return Booking(
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
            guest_details=[g.model_dump() for g in payload.guest_details],
            commission_snapshot=pricing.commission_amount,
            commission_percent_snapshot=pricing.commission_percent,
            agent_discount_percent_snapshot=(
                pricing.agent_discount_percent if is_b2b else None
            ),
        )
