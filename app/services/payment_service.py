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
from app.services.booking_visibility import (
    admin_owns_booking_sanatorium,
    booking_visibility_clauses,
)
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

        # The same visibility rule as GET /bookings/{id}. Checking only the
        # customer role would let an agent or the transfer operator open a
        # payment against any booking id they can guess.
        stmt = select(Booking).where(Booking.id == booking_id)
        for clause in booking_visibility_clauses(user):
            stmt = stmt.where(clause)
        booking = await self.db.scalar(stmt)
        if booking is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No booking found with this id under your account",
            )
        if booking.status == BookingStatus.CANCELLED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "This booking was cancelled, so it cannot be paid. "
                    "Please make a new booking."
                ),
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
                detail="This booking has already been paid in full.",
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
        # confirms it — which is already the status a new booking carries, so
        # there is nothing to move here. Forcing PENDING would have undone a
        # confirmation that some other payment had legitimately made.
        self.db.add(payment)
        await self.db.commit()
        await self.db.refresh(payment)
        return payment

    async def confirm_cash(self, payment_id: uuid.UUID, user: User) -> Payment:
        if user.role not in (UserRole.ADMIN, UserRole.SUPER_ADMIN):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Only a property administrator or a platform administrator "
                    "can confirm a cash payment."
                ),
            )
        payment = await self.db.get(Payment, payment_id)
        if payment is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No payment found with this id",
            )
        if payment.method != PaymentMethod.CASH:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"This is a {payment.method} payment. Only cash payments "
                    "are confirmed here; card payments settle through the "
                    "payment provider."
                ),
            )
        if payment.status == PaymentStatus.PAID:
            return payment
        # Cancelling a booking cancels its pending intents; re-confirming one
        # would record money against a stay nobody is having.
        if payment.status != PaymentStatus.PENDING:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"This payment is {payment.status}; only a pending cash "
                    "payment can be confirmed."
                ),
            )

        booking = await self.db.get(Booking, payment.booking_id)
        # A property admin may only settle money for their own property.
        if (
            booking is not None
            and user.role == UserRole.ADMIN
            and not await admin_owns_booking_sanatorium(self.db, booking, user.id)
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This payment belongs to a booking at another property.",
            )
        if booking is not None and booking.status == BookingStatus.CANCELLED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "This booking was cancelled, so its payment cannot be confirmed."
                ),
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
