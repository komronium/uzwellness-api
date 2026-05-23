import logging
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.sanatorium_lookup import sanatorium_name_for_booking
from app.integrations.payment_gateways import (
    WebhookResult,
    get_gateway,
)
from app.models.booking import Booking, BookingStatus
from app.models.payment import Payment, PaymentMethod, PaymentStatus
from app.models.user import User, UserRole
from app.services.email_service import BookingEmailContext, send_booking_confirmed

logger = logging.getLogger(__name__)


class PaymentService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def initiate(
        self, booking_id: uuid.UUID, method: PaymentMethod, user: User
    ) -> tuple[Payment, str | None]:
        booking = await self.db.get(Booking, booking_id)
        if booking is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found"
            )
        if user.role == UserRole.CUSTOMER and booking.user_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not allowed to pay for this booking",
            )
        if booking.status == BookingStatus.CANCELLED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot pay for a cancelled booking",
            )

        merchant_trans_id = uuid.uuid4().hex
        gateway = get_gateway(method)
        redirect_url = gateway.build_checkout_url(
            amount=booking.final_price,
            currency=booking.currency,
            merchant_trans_id=merchant_trans_id,
        )

        payment = Payment(
            booking_id=booking.id,
            method=method,
            amount=booking.final_price,
            currency=booking.currency,
            merchant_trans_id=merchant_trans_id,
        )
        if method == PaymentMethod.CASH:
            booking.status = BookingStatus.PENDING
            payment.status = PaymentStatus.PENDING

        self.db.add(payment)
        await self.db.commit()
        await self.db.refresh(payment)
        return payment, redirect_url

    async def confirm_cash(self, payment_id: uuid.UUID, user: User) -> Payment:
        if user.role not in (UserRole.ADMIN, UserRole.SUPER_ADMIN):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admin/super_admin can confirm cash payments",
            )
        payment = await self.db.get(Payment, payment_id)
        if payment is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found"
            )
        if payment.method != PaymentMethod.CASH:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only cash payments can be confirmed here",
            )
        if payment.status == PaymentStatus.PAID:
            return payment
        await self._mark_paid(
            payment,
            provider_payment_id=f"cash:{user.id}",
            raw_payload={"confirmed_by": str(user.id)},
        )
        return payment

    async def handle_webhook(
        self,
        method: PaymentMethod,
        *,
        payload: dict,
        headers: Mapping[str, str],
    ) -> dict:
        gateway = get_gateway(method)
        if not gateway.verify_webhook(payload=payload, headers=headers):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid webhook signature",
            )
        result = gateway.parse_webhook(payload=payload)
        payment = await self._find_by_trans_id(result.merchant_trans_id)
        if payment is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found"
            )
        await self._apply_webhook_result(payment, result, payload)
        return result.response_body

    async def _apply_webhook_result(
        self, payment: Payment, result: WebhookResult, payload: dict
    ) -> None:
        if result.is_paid:
            await self._mark_paid(
                payment,
                provider_payment_id=result.provider_payment_id,
                raw_payload=payload,
            )
        elif result.is_failed:
            payment.status = PaymentStatus.FAILED
            payment.raw_payload = {**(payment.raw_payload or {}), **payload}
            await self.db.commit()

    async def _find_by_trans_id(self, merchant_trans_id: str) -> Payment | None:
        return await self.db.scalar(
            select(Payment).where(
                Payment.merchant_trans_id == str(merchant_trans_id)
            )
        )

    async def _mark_paid(
        self,
        payment: Payment,
        *,
        provider_payment_id: str | None,
        raw_payload: dict,
    ) -> None:
        if payment.status == PaymentStatus.PAID:
            return
        payment.status = PaymentStatus.PAID
        payment.provider_payment_id = provider_payment_id
        payment.paid_at = datetime.now(UTC)
        payment.raw_payload = {**(payment.raw_payload or {}), **raw_payload}

        booking = await self.db.get(Booking, payment.booking_id)
        if booking is not None and booking.status != BookingStatus.CANCELLED:
            booking.status = BookingStatus.CONFIRMED

        await self.db.commit()
        if booking is not None:
            await self._send_confirmation_email(booking)

    async def _send_confirmation_email(self, booking: Booking) -> None:
        if booking.user_id is None:
            return
        user = await self.db.get(User, booking.user_id)
        if user is None or not user.email:
            return
        sanatorium_name = await sanatorium_name_for_booking(self.db, booking)
        if sanatorium_name is None:
            return
        send_booking_confirmed(
            to=user.email,
            ctx=BookingEmailContext(
                booking_code=booking.code,
                sanatorium_name=sanatorium_name,
                check_in=booking.check_in,
                check_out=booking.check_out,
                guest_name=user.full_name or user.email,
                total_price=booking.final_price,
                currency=booking.currency,
            ),
        )


def get_payment_service(
    db: AsyncSession = Depends(get_db),
) -> PaymentService:
    return PaymentService(db)
