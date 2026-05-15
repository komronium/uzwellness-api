import base64
import hashlib
import hmac
import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from urllib.parse import urlencode

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.amenity import TreatmentProgram
from app.models.booking import Booking, BookingStatus
from app.models.payment import Payment, PaymentMethod, PaymentStatus
from app.models.room import Room
from app.models.sanatorium import Sanatorium
from app.models.user import User, UserRole
from app.services.email_service import (
    BookingEmailContext,
    send_booking_confirmed,
)

logger = logging.getLogger(__name__)

_PAYME_AMOUNT_FACTOR = Decimal("100")


class PaymentService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def initiate(
        self, booking_id: uuid.UUID, method: PaymentMethod, user: User
    ) -> tuple[Payment, str | None]:
        booking = (await self.db.execute(
            select(Booking).where(Booking.id == booking_id)
        )).scalar_one_or_none()
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
        payment = Payment(
            booking_id=booking.id,
            method=method,
            amount=booking.final_price,
            currency=booking.currency,
            merchant_trans_id=merchant_trans_id,
        )

        redirect_url: str | None = None
        if method == PaymentMethod.PAYME:
            redirect_url = _build_payme_url(booking, merchant_trans_id)
        elif method == PaymentMethod.CLICK:
            redirect_url = _build_click_url(booking, merchant_trans_id)
        elif method == PaymentMethod.CASH:
            booking.status = BookingStatus.PENDING
            payment.status = PaymentStatus.PENDING

        self.db.add(payment)
        await self.db.commit()
        await self.db.refresh(payment)
        return payment, redirect_url

    async def handle_payme_webhook(self, payload: dict, raw_body: bytes, auth_header: str | None) -> dict:
        if settings.PAYME_MERCHANT_KEY:
            if not _check_payme_auth(auth_header, settings.PAYME_MERCHANT_KEY):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid webhook signature",
                )

        params = payload.get("params") or {}
        merchant_trans_id = (
            params.get("account", {}).get("order_id")
            or params.get("merchant_trans_id")
            or params.get("id")
        )
        if not merchant_trans_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing merchant_trans_id",
            )

        payment = await self._find_by_trans_id(merchant_trans_id)
        if payment is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found"
            )
        await self._mark_paid(
            payment,
            provider_payment_id=params.get("id"),
            raw_payload=payload,
        )
        return {"result": {"state": 2}}

    async def handle_click_webhook(self, payload: dict) -> dict:
        sign_string = payload.get("sign_string")
        if settings.CLICK_SECRET_KEY and sign_string:
            expected = _click_sign(payload, settings.CLICK_SECRET_KEY)
            if not hmac.compare_digest(sign_string, expected):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid webhook signature",
                )

        merchant_trans_id = payload.get("merchant_trans_id")
        if not merchant_trans_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing merchant_trans_id",
            )

        payment = await self._find_by_trans_id(merchant_trans_id)
        if payment is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found"
            )

        action = int(payload.get("action", 0))
        error = int(payload.get("error", 0))
        if action == 1 and error == 0:
            await self._mark_paid(
                payment,
                provider_payment_id=str(payload.get("click_trans_id", "")),
                raw_payload=payload,
            )
        elif error != 0:
            payment.status = PaymentStatus.FAILED
            payment.raw_payload = {**(payment.raw_payload or {}), **payload}
            await self.db.commit()

        return {"error": 0, "error_note": "Success"}

    async def _find_by_trans_id(self, merchant_trans_id: str) -> Payment | None:
        return (await self.db.execute(
            select(Payment).where(Payment.merchant_trans_id == str(merchant_trans_id))
        )).scalar_one_or_none()

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
        sanatorium_name = await self._lookup_sanatorium_name(booking)
        if sanatorium_name is None:
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
        send_booking_confirmed(to=user.email, ctx=ctx)

    async def _lookup_sanatorium_name(self, booking: Booking) -> str | None:
        if booking.room_id is not None:
            return (await self.db.execute(
                select(Sanatorium.name)
                .join(Room, Room.sanatorium_id == Sanatorium.id)
                .where(Room.id == booking.room_id)
            )).scalar_one_or_none()
        if booking.program_id is not None:
            return (await self.db.execute(
                select(Sanatorium.name)
                .join(TreatmentProgram, TreatmentProgram.sanatorium_id == Sanatorium.id)
                .where(TreatmentProgram.id == booking.program_id)
            )).scalar_one_or_none()
        return None


def _build_payme_url(booking: Booking, merchant_trans_id: str) -> str:
    if not settings.PAYME_MERCHANT_ID:
        return f"{settings.PAYME_CHECKOUT_URL}?order_id={merchant_trans_id}"
    amount_tiyin = int((Decimal(booking.final_price) * _PAYME_AMOUNT_FACTOR).to_integral_value())
    params = f"m={settings.PAYME_MERCHANT_ID};ac.order_id={merchant_trans_id};a={amount_tiyin}"
    encoded = base64.b64encode(params.encode("utf-8")).decode("ascii")
    return f"{settings.PAYME_CHECKOUT_URL}{encoded}"


def _build_click_url(booking: Booking, merchant_trans_id: str) -> str:
    if not settings.CLICK_SERVICE_ID:
        return f"{settings.CLICK_CHECKOUT_URL}?merchant_trans_id={merchant_trans_id}"
    query = urlencode({
        "service_id": settings.CLICK_SERVICE_ID,
        "merchant_id": settings.CLICK_MERCHANT_ID,
        "amount": str(booking.final_price),
        "transaction_param": merchant_trans_id,
    })
    return f"{settings.CLICK_CHECKOUT_URL}?{query}"


def _check_payme_auth(auth_header: str | None, secret: str) -> bool:
    if not auth_header or not auth_header.lower().startswith("basic "):
        return False
    try:
        decoded = base64.b64decode(auth_header.split(" ", 1)[1]).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return False
    _, _, password = decoded.partition(":")
    return hmac.compare_digest(password, secret)


def _click_sign(payload: dict, secret: str) -> str:
    parts = [
        str(payload.get("click_trans_id", "")),
        str(payload.get("service_id", "")),
        secret,
        str(payload.get("merchant_trans_id", "")),
        str(payload.get("amount", "")),
        str(payload.get("action", "")),
        str(payload.get("sign_time", "")),
    ]
    return hashlib.md5("".join(parts).encode("utf-8")).hexdigest()  # noqa: S324 — Click protocol uses MD5


def get_payment_service(db: AsyncSession = Depends(get_db)) -> PaymentService:
    return PaymentService(db)
