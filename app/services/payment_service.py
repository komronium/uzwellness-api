import logging
import uuid
from datetime import UTC, datetime

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.sanatorium_lookup import sanatorium_name_for_booking
from app.models.booking import Booking, BookingStatus
from app.models.payment import Payment, PaymentMethod, PaymentStatus
from app.models.user import User, UserRole
from app.services.email_service import BookingEmailContext, send_booking_confirmed

logger = logging.getLogger(__name__)


async def send_booking_confirmed_email(db: AsyncSession, booking: Booking) -> None:
    """Best-effort "payment received" email; missing data simply skips it."""

    if booking.user_id is None:
        return
    user = await db.get(User, booking.user_id)
    if user is None or not user.email:
        return
    sanatorium_name = await sanatorium_name_for_booking(db, booking)
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


class PaymentService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def initiate(
        self, booking_id: uuid.UUID, method: PaymentMethod, user: User
    ) -> Payment:
        """Register an offline (cash) payment intent for a booking.

        Uzum payments are not initiated here: the customer starts them in the
        Uzum Bank app and Uzum drives ``/payments/uzum/*``. Callers should read
        ``GET /payments/uzum/order/{booking_id}`` for what to show the guest.
        """

        if method != PaymentMethod.CASH:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Only cash payments can be initiated from the API; Uzum "
                    "payments start in the Uzum Bank app — see "
                    "GET /payments/uzum/order/{booking_id}"
                ),
            )

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
        already_paid = await self.db.scalar(
            select(Payment).where(
                Payment.booking_id == booking.id,
                Payment.status == PaymentStatus.PAID,
            )
        )
        if already_paid is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Booking is already paid",
            )

        payment = Payment(
            booking_id=booking.id,
            method=method,
            status=PaymentStatus.PENDING,
            amount=booking.final_price,
            currency=booking.currency,
            merchant_trans_id=booking.reservation_number,
        )
        # Cash is collected on arrival, so the stay stays unpaid until an admin
        # confirms it.
        if booking.status != BookingStatus.COMPLETED:
            booking.status = BookingStatus.PENDING
        self.db.add(payment)
        await self.db.commit()
        await self.db.refresh(payment)
        return payment

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
        # Cancelling a booking cancels its pending intents; re-confirming one
        # would record money against a stay nobody is having.
        if payment.status != PaymentStatus.PENDING:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Payment is {payment.status}, only pending cash can be confirmed",
            )

        booking = await self.db.get(Booking, payment.booking_id)
        if booking is not None and booking.status == BookingStatus.CANCELLED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot confirm payment for a cancelled booking",
            )

        payment.status = PaymentStatus.PAID
        payment.provider_payment_id = f"cash:{user.id}"
        payment.paid_at = datetime.now(UTC)
        payment.raw_payload = {
            **(payment.raw_payload or {}),
            "confirmed_by": str(user.id),
        }

        if booking is not None and booking.status == BookingStatus.PENDING:
            booking.status = BookingStatus.CONFIRMED
        await self.db.commit()
        if booking is not None:
            await send_booking_confirmed_email(self.db, booking)
        return payment


def get_payment_service(
    db: AsyncSession = Depends(get_db),
) -> PaymentService:
    return PaymentService(db)
