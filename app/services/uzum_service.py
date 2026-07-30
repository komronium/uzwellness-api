"""Uzum Bank Merchant API — partner-side webhook handlers.

The customer pays inside the Uzum Bank app: they pick our service, type the
reservation number and Uzum drives us through ``/check`` → ``/create`` →
``/confirm``. Everything here is therefore *inbound*; we never call Uzum.

Transaction states map onto the existing ``payments`` rows:

    Uzum CREATED   → PaymentStatus.PENDING
    Uzum CONFIRMED → PaymentStatus.PAID
    Uzum REVERSED  → PaymentStatus.CANCELLED (never paid)
                     PaymentStatus.REFUNDED  (reversed after confirmation)
    expired        → PaymentStatus.FAILED

Spec: https://developer.uzumbank.uz/merchant
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from fastapi import Depends
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.sanatorium_lookup import sanatorium_name_for_booking
from app.integrations.uzum import UzumError, UzumErrorCode, verify_service_id
from app.models.booking import Booking, BookingStatus
from app.models.payment import Payment, PaymentMethod, PaymentStatus
from app.models.user import User
from app.schemas.uzum import (
    UzumCheckRequest,
    UzumCheckResponse,
    UzumConfirmRequest,
    UzumConfirmResponse,
    UzumCreateRequest,
    UzumCreateResponse,
    UzumData,
    UzumReverseRequest,
    UzumReverseResponse,
    UzumStatusRequest,
    UzumStatusResponse,
)
from app.services.exchange_rate_service import ExchangeRateService
from app.services.payment_service import send_booking_confirmed_email

logger = logging.getLogger("uzwellness.uzum")

# Keys the Uzum app may use for the identifier the customer types in. The
# first one is what we register with Uzum; the rest are accepted so a field
# renamed on their side cannot break payments. Whatever the key, the value is
# looked up as a reservation number or booking code — never as a user id.
_ORDER_ID_KEYS = (
    "order_id",
    "orderId",
    "account",
    "user_id",
    "userId",
    "booking_code",
    "code",
)

_TIYIN = Decimal("100")
UZUM_CURRENCY = "UZS"


def now_ms() -> int:
    return int(datetime.now(UTC).timestamp() * 1000)


def to_ms(moment: datetime | None) -> int | None:
    if moment is None:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return int(moment.timestamp() * 1000)


class UzumService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # --- webhooks ------------------------------------------------------------

    async def check(self, payload: UzumCheckRequest) -> UzumCheckResponse:
        verify_service_id(payload.service_id)
        booking = await self._booking_for_params(payload.params)
        await self._assert_payable(booking)
        return UzumCheckResponse(
            service_id=payload.service_id,
            timestamp=now_ms(),
            data=await self._booking_data(booking),
        )

    async def create(self, payload: UzumCreateRequest) -> UzumCreateResponse:
        verify_service_id(payload.service_id)
        if payload.amount <= 0:
            raise UzumError(UzumErrorCode.INVALID_AMOUNT, "Amount must be positive")

        existing = await self._find_payment(payload.trans_id)
        if existing is not None:
            raise UzumError(
                UzumErrorCode.TRANSACTION_ALREADY_CREATED,
                f"transId {payload.trans_id} already exists",
            )

        # Lock the booking so two Uzum transactions cannot be opened for the
        # same reservation at once.
        booking = await self._booking_for_params(payload.params, lock=True)
        await self._expire_stale_transactions(booking.id)
        await self._assert_payable(booking)

        expected = await self.expected_amount_tiyin(booking)
        if payload.amount != expected:
            raise UzumError(
                UzumErrorCode.INVALID_AMOUNT,
                f"Expected {expected} tiyin for booking {booking.code}, "
                f"got {payload.amount}",
            )

        payment = Payment(
            booking_id=booking.id,
            method=PaymentMethod.UZUM,
            status=PaymentStatus.PENDING,
            amount=Decimal(payload.amount) / _TIYIN,
            currency=UZUM_CURRENCY,
            merchant_trans_id=booking.reservation_number,
            provider_payment_id=payload.trans_id,
            raw_payload={"create": payload.model_dump(mode="json", by_alias=True)},
        )
        self.db.add(payment)
        try:
            await self.db.commit()
        except IntegrityError as exc:
            # Concurrent /create with the same transId lost the race.
            await self.db.rollback()
            raise UzumError(
                UzumErrorCode.TRANSACTION_ALREADY_CREATED,
                f"transId {payload.trans_id} already exists",
            ) from exc
        await self.db.refresh(payment)

        return UzumCreateResponse(
            service_id=payload.service_id,
            trans_id=payload.trans_id,
            trans_time=to_ms(payment.created_at) or now_ms(),
            data=await self._booking_data(booking),
            amount=payload.amount,
        )

    async def confirm(self, payload: UzumConfirmRequest) -> UzumConfirmResponse:
        verify_service_id(payload.service_id)
        payment = await self._require_payment(payload.trans_id, lock=True)

        if payment.status == PaymentStatus.PAID:
            raise UzumError(
                UzumErrorCode.TRANSACTION_ALREADY_CONFIRMED, str(payment.id)
            )
        if payment.status in (
            PaymentStatus.CANCELLED,
            PaymentStatus.REFUNDED,
            PaymentStatus.REFUND_PENDING,
            PaymentStatus.FAILED,
        ):
            raise UzumError(
                UzumErrorCode.TRANSACTION_CANCELLED,
                f"payment {payment.id} is {payment.status}",
            )
        if self._is_expired(payment):
            payment.status = PaymentStatus.FAILED
            await self.db.commit()
            raise UzumError(
                UzumErrorCode.TRANSACTION_CANCELLED,
                f"payment {payment.id} expired before confirmation",
            )

        booking = await self.db.get(Booking, payment.booking_id)
        if booking is None or booking.status == BookingStatus.CANCELLED:
            raise UzumError(
                UzumErrorCode.TRANSACTION_CANCELLED,
                f"booking for payment {payment.id} is cancelled",
            )

        payment.status = PaymentStatus.PAID
        payment.paid_at = datetime.now(UTC)
        payment.raw_payload = {
            **(payment.raw_payload or {}),
            "confirm": payload.model_dump(mode="json", by_alias=True),
        }
        if booking.status == BookingStatus.PENDING:
            booking.status = BookingStatus.CONFIRMED
        await self.db.commit()

        await send_booking_confirmed_email(self.db, booking)

        return UzumConfirmResponse(
            service_id=payload.service_id,
            trans_id=payload.trans_id,
            confirm_time=to_ms(payment.paid_at) or now_ms(),
            data=await self._booking_data(booking),
            amount=self._amount_tiyin(payment),
        )

    async def reverse(self, payload: UzumReverseRequest) -> UzumReverseResponse:
        verify_service_id(payload.service_id)
        payment = await self._require_payment(payload.trans_id, lock=True)

        if payment.status in (PaymentStatus.CANCELLED, PaymentStatus.REFUNDED):
            raise UzumError(UzumErrorCode.TRANSACTION_ALREADY_REVERSED, str(payment.id))
        if payment.status == PaymentStatus.FAILED:
            raise UzumError(
                UzumErrorCode.TRANSACTION_NOT_REVERSIBLE,
                f"payment {payment.id} already failed",
            )

        was_paid = payment.status in (
            PaymentStatus.PAID,
            PaymentStatus.REFUND_PENDING,
        )
        payment.status = PaymentStatus.REFUNDED if was_paid else PaymentStatus.CANCELLED
        payment.cancelled_at = datetime.now(UTC)
        payment.raw_payload = {
            **(payment.raw_payload or {}),
            "reverse": payload.model_dump(mode="json", by_alias=True),
        }

        booking = await self.db.get(Booking, payment.booking_id)
        if (
            was_paid
            and booking is not None
            and booking.status == BookingStatus.CONFIRMED
        ):
            # The money went back to the customer, so the stay is unpaid again.
            booking.status = BookingStatus.PENDING
        await self.db.commit()

        data = await self._booking_data(booking) if booking is not None else {}
        return UzumReverseResponse(
            service_id=payload.service_id,
            trans_id=payload.trans_id,
            reverse_time=to_ms(payment.cancelled_at) or now_ms(),
            data=data,
            amount=self._amount_tiyin(payment),
        )

    async def status(self, payload: UzumStatusRequest) -> UzumStatusResponse:
        verify_service_id(payload.service_id)
        payment = await self._require_payment(payload.trans_id, lock=True)

        if payment.status == PaymentStatus.PENDING and self._is_expired(payment):
            payment.status = PaymentStatus.FAILED
            await self.db.commit()

        state = _STATUS_MAP.get(payment.status)
        if state is None:
            raise UzumError(
                UzumErrorCode.TRANSACTION_NOT_FOUND,
                f"payment {payment.id} is {payment.status}",
            )

        booking = await self.db.get(Booking, payment.booking_id)
        return UzumStatusResponse(
            service_id=payload.service_id,
            trans_id=payload.trans_id,
            status=state,
            trans_time=to_ms(payment.created_at) or now_ms(),
            confirm_time=to_ms(payment.paid_at),
            reverse_time=to_ms(payment.cancelled_at),
            data=await self._booking_data(booking) if booking is not None else {},
            amount=self._amount_tiyin(payment),
        )

    # --- pricing -------------------------------------------------------------

    async def expected_amount_tiyin(self, booking: Booking) -> int:
        """Booking total in tiyin — Uzum only settles in UZS."""

        amount_uzs = await self.expected_amount_uzs(booking)
        return int((amount_uzs * _TIYIN).to_integral_value(ROUND_HALF_UP))

    async def expected_amount_uzs(self, booking: Booking) -> Decimal:
        if booking.currency.upper() == UZUM_CURRENCY:
            return booking.final_price
        converter = await ExchangeRateService(self.db).get_converter(UZUM_CURRENCY)
        amount = converter.convert(booking.final_price, booking.currency, UZUM_CURRENCY)
        if amount is None:
            logger.error(
                "No %s_UZS exchange rate; cannot price booking %s for Uzum",
                booking.currency,
                booking.code,
            )
            raise UzumError(
                UzumErrorCode.INTERNAL_ERROR,
                f"Missing {booking.currency}_UZS exchange rate",
            )
        return amount

    # --- lookups -------------------------------------------------------------

    async def find_booking(self, order_id: str) -> Booking | None:
        return await self._load_booking(order_id, lock=False)

    async def _booking_for_params(self, params: dict, *, lock: bool = False) -> Booking:
        order_id = _order_id_from_params(params)
        booking = await self._load_booking(order_id, lock=lock)
        if booking is None:
            raise UzumError(
                UzumErrorCode.ACCOUNT_NOT_FOUND, f"No booking for order_id {order_id}"
            )
        return booking

    async def _load_booking(self, order_id: str, *, lock: bool) -> Booking | None:
        stmt = select(Booking).where(
            or_(
                Booking.reservation_number == order_id,
                Booking.code == order_id.upper(),
            )
        )
        if lock:
            stmt = stmt.with_for_update()
        return await self.db.scalar(stmt)

    async def _find_payment(
        self, trans_id: str, *, lock: bool = False
    ) -> Payment | None:
        stmt = select(Payment).where(
            Payment.method == PaymentMethod.UZUM,
            Payment.provider_payment_id == trans_id,
        )
        if lock:
            stmt = stmt.with_for_update()
        return await self.db.scalar(stmt)

    async def _require_payment(self, trans_id: str, *, lock: bool = False) -> Payment:
        payment = await self._find_payment(trans_id, lock=lock)
        if payment is None:
            raise UzumError(
                UzumErrorCode.TRANSACTION_NOT_FOUND, f"transId {trans_id} is unknown"
            )
        return payment

    # --- state helpers -------------------------------------------------------

    async def _assert_payable(self, booking: Booking) -> None:
        if booking.status == BookingStatus.CANCELLED:
            raise UzumError(
                UzumErrorCode.PAYMENT_CANCELLED, f"booking {booking.code} is cancelled"
            )
        settled = await self.db.scalar(
            select(Payment).where(
                Payment.booking_id == booking.id,
                Payment.status.in_((PaymentStatus.PAID, PaymentStatus.REFUND_PENDING)),
            )
        )
        if settled is not None:
            raise UzumError(
                UzumErrorCode.ALREADY_PAID, f"booking {booking.code} is already paid"
            )
        # A pending *cash* intent is not a payment, but a live Uzum transaction
        # is — opening a second one risks charging the guest twice.
        in_flight = await self.db.scalar(
            select(Payment).where(
                Payment.booking_id == booking.id,
                Payment.method == PaymentMethod.UZUM,
                Payment.status == PaymentStatus.PENDING,
            )
        )
        if in_flight is not None:
            raise UzumError(
                UzumErrorCode.ALREADY_PAID,
                f"booking {booking.code} has transaction "
                f"{in_flight.provider_payment_id} in progress",
            )

    async def _expire_stale_transactions(self, booking_id) -> None:
        """Fail transactions Uzum never confirmed, freeing the booking."""

        cutoff = self._expiry_cutoff()
        stale = (
            await self.db.scalars(
                select(Payment).where(
                    Payment.booking_id == booking_id,
                    Payment.method == PaymentMethod.UZUM,
                    Payment.status == PaymentStatus.PENDING,
                    Payment.created_at < cutoff,
                )
            )
        ).all()
        if not stale:
            return
        for payment in stale:
            payment.status = PaymentStatus.FAILED
            logger.info("Expired Uzum transaction %s", payment.provider_payment_id)
        await self.db.commit()

    def _is_expired(self, payment: Payment) -> bool:
        created = payment.created_at
        if created is None:
            return False
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        return created < self._expiry_cutoff()

    @staticmethod
    def _expiry_cutoff() -> datetime:
        return datetime.now(UTC) - timedelta(
            minutes=settings.UZUM_TRANSACTION_TIMEOUT_MINUTES
        )

    @staticmethod
    def _amount_tiyin(payment: Payment) -> int:
        return int((payment.amount * _TIYIN).to_integral_value(ROUND_HALF_UP))

    async def _booking_data(self, booking: Booking) -> UzumData:
        """Key/value pairs Uzum renders in the app before the customer pays."""

        data: UzumData = {
            "order_id": {"value": booking.reservation_number},
            "check_in": {"value": booking.check_in.isoformat()},
            "check_out": {"value": booking.check_out.isoformat()},
        }
        sanatorium_name = await sanatorium_name_for_booking(self.db, booking)
        if sanatorium_name:
            data["property"] = {"value": sanatorium_name}
        guest = await self._guest_name(booking)
        if guest:
            data["guest"] = {"value": guest}
        return data

    async def _guest_name(self, booking: Booking) -> str | None:
        if booking.user_id is None:
            return None
        user = await self.db.get(User, booking.user_id)
        if user is None:
            return None
        return user.full_name or user.email


_STATUS_MAP: dict[PaymentStatus, str] = {
    PaymentStatus.PENDING: "CREATED",
    PaymentStatus.PAID: "CONFIRMED",
    PaymentStatus.REFUND_PENDING: "CONFIRMED",
    PaymentStatus.CANCELLED: "REVERSED",
    PaymentStatus.REFUNDED: "REVERSED",
}


def _order_id_from_params(params: dict) -> str:
    for key in _ORDER_ID_KEYS:
        value = params.get(key)
        if value is None:
            continue
        order_id = str(value).strip()
        if order_id:
            return order_id
    raise UzumError(
        UzumErrorCode.MISSING_PARAMETERS,
        f"params must contain one of {', '.join(_ORDER_ID_KEYS)}",
    )


def get_uzum_service(db: AsyncSession = Depends(get_db)) -> UzumService:
    return UzumService(db)
