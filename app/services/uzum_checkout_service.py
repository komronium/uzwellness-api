"""Uzum Checkout — card payments started on our own site.

Two halves live here:

* **Outbound.** ``start()`` registers an order with Uzum and hands back the
  payment page URL the guest is sent to.
* **Inbound.** The three callbacks are recorded verbatim, then *verified*:
  Checkout signs nothing, so a callback body is never applied as-is. It only
  tells us which order changed; the state that is written to the payment comes
  from calling ``/payment/getOrderStatus`` back. A callback we could not
  verify stays with ``processed_at = NULL`` and is acknowledged anyway, so
  Uzum stops retrying and the row remains for a later sweep.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.ids import uuid7
from app.core.sanatorium_lookup import sanatorium_name_for_booking
from app.integrations.uzum.checkout import (
    ORDER_COMPLETED,
    ORDER_DECLINED,
    ORDER_REFUNDED,
    ORDER_REGISTERED,
    UzumCheckoutApiError,
    UzumCheckoutClient,
    pick_order_id,
    pick_payment_url,
    pick_status,
)
from app.models.booking import Booking, BookingStatus
from app.models.payment import Payment, PaymentMethod, PaymentStatus
from app.models.user import User, UserRole
from app.models.uzum_checkout_event import UzumCheckoutCallbackKind, UzumCheckoutEvent
from app.schemas.uzum_checkout import (
    AcquiringCallback,
    BusinessEventCallback,
    CheckoutSessionRead,
    ReceiptCallback,
)
from app.services.exchange_rate_service import ExchangeRateService
from app.services.payment_service import send_booking_confirmed_email

logger = logging.getLogger("uzwellness.uzum_checkout")

CHECKOUT_CURRENCY = "UZS"
_TIYIN = Decimal("100")


def client_ip(request: Request) -> str | None:
    """Best-effort source address, for observability and the nginx allowlist.

    Behind nginx the socket peer is always local, so the forwarded header is
    the only useful signal. It is spoofable and therefore recorded, never
    trusted for authorization — that belongs in nginx, above this process.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return request.client.host[:64] if request.client else None


class UzumCheckoutService:
    def __init__(
        self, db: AsyncSession, client: UzumCheckoutClient | None = None
    ) -> None:
        self.db = db
        self.client = client or UzumCheckoutClient.from_settings()

    # --- outbound: registering a payment -------------------------------------

    async def start(
        self,
        booking_id: uuid.UUID,
        user: User,
        *,
        locale: str | None = None,
    ) -> CheckoutSessionRead:
        """Register the booking's total with Uzum and return the form URL."""

        if not settings.uzum_checkout_enabled:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Uzum Checkout is not configured",
            )

        booking = await self.db.scalar(
            select(Booking).where(Booking.id == booking_id).with_for_update()
        )
        if booking is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found"
            )
        self._assert_may_pay(booking, user)
        await self._assert_unpaid(booking)

        # An earlier attempt may still be open on Uzum's side; reuse its form
        # instead of registering a second order for the same booking.
        reusable = await self._reusable_session(booking)
        if reusable is not None:
            return reusable

        amount_uzs = await self._amount_uzs(booking)
        amount_tiyin = int((amount_uzs * _TIYIN).to_integral_value(ROUND_HALF_UP))
        if amount_tiyin <= 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Booking total must be positive to pay online",
            )

        payment_id = uuid7()
        order_number = _order_number(booking, payment_id)
        details = await self._payment_details(booking)
        cart = self._cart(payment_id, booking, amount_tiyin, details)

        try:
            result = await self.client.register(
                amount_tiyin=amount_tiyin,
                client_id=str(booking.user_id or booking.id),
                order_number=order_number,
                payment_details=details,
                locale=locale,
                cart=cart,
            )
        except UzumCheckoutApiError as exc:
            logger.warning(
                "Uzum Checkout register failed for booking %s: %s", booking.code, exc
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Uzum Checkout rejected the payment: {exc.message}"[:500],
            ) from exc

        order_id = pick_order_id(result)
        payment_url = pick_payment_url(result)
        if not order_id or not payment_url:
            logger.error("Uzum Checkout register returned %s", result)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Uzum Checkout did not return a payment URL",
            )

        payment = Payment(
            id=payment_id,
            booking_id=booking.id,
            method=PaymentMethod.UZUM_CHECKOUT,
            status=PaymentStatus.PENDING,
            amount=amount_uzs,
            currency=CHECKOUT_CURRENCY,
            merchant_trans_id=order_number,
            provider_payment_id=order_id,
            raw_payload={"register": result},
        )
        self.db.add(payment)
        await self.db.commit()
        await self.db.refresh(payment)
        logger.info(
            "Uzum Checkout order %s registered for booking %s (%s tiyin)",
            order_id,
            booking.code,
            amount_tiyin,
        )
        return CheckoutSessionRead(
            payment_id=payment.id,
            booking_id=booking.id,
            order_id=order_id,
            order_number=order_number,
            payment_url=payment_url,
            amount=payment.amount,
            status=payment.status,
        )

    # --- outbound: settling a payment ----------------------------------------

    async def sync_order(self, order_id: str) -> Payment | None:
        """Ask Uzum what happened to an order and write the answer down.

        This is the only path that moves a Checkout payment out of ``pending``:
        callbacks merely say "look at this order".
        """

        payment = await self._payment_for_order(order_id, lock=True)
        if payment is None:
            logger.info("Uzum Checkout order %s matches no payment", order_id)
            return None
        result = await self.client.get_order_status(order_id)
        await self._apply(payment, pick_status(result), result)
        return payment

    async def refresh(self, payment_id: uuid.UUID, user: User) -> tuple[Payment, str]:
        """Re-read one payment's state from Uzum, for the guest's status page."""

        payment = await self.db.get(Payment, payment_id)
        if payment is None or payment.method != PaymentMethod.UZUM_CHECKOUT:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found"
            )
        booking = await self.db.get(Booking, payment.booking_id)
        if booking is not None:
            self._assert_may_pay(booking, user)
        if not payment.provider_payment_id:
            return payment, ""
        try:
            result = await self.client.get_order_status(payment.provider_payment_id)
        except UzumCheckoutApiError as exc:
            # The stored state is still meaningful, so report it rather than
            # failing the guest's status poll outright.
            logger.warning("Uzum Checkout status lookup failed: %s", exc)
            return payment, ""
        order_status = pick_status(result) or ""
        await self._apply(payment, order_status, result)
        return payment, order_status

    async def _apply(
        self, payment: Payment, order_status: str | None, result: dict
    ) -> None:
        """Move the payment (and its booking) to match Uzum's order state."""

        if order_status is None:
            logger.warning(
                "Uzum Checkout order %s has no status in %s",
                payment.provider_payment_id,
                result,
            )
            return
        payment.raw_payload = {**(payment.raw_payload or {}), "status": result}

        confirmed = False
        if order_status == ORDER_COMPLETED:
            if payment.status != PaymentStatus.PAID:
                payment.status = PaymentStatus.PAID
                payment.paid_at = datetime.now(UTC)
                confirmed = True
        elif order_status == ORDER_REFUNDED:
            payment.status = PaymentStatus.REFUNDED
            payment.cancelled_at = datetime.now(UTC)
        elif order_status == ORDER_DECLINED:
            if payment.status == PaymentStatus.PENDING:
                payment.status = PaymentStatus.FAILED
        elif order_status != ORDER_REGISTERED:
            logger.info(
                "Uzum Checkout order %s in unhandled state %s",
                payment.provider_payment_id,
                order_status,
            )

        booking = await self.db.get(Booking, payment.booking_id)
        if (
            confirmed
            and booking is not None
            and booking.status == BookingStatus.PENDING
        ):
            booking.status = BookingStatus.CONFIRMED
        await self.db.commit()
        if confirmed and booking is not None:
            await send_booking_confirmed_email(self.db, booking)

    # --- inbound: callbacks --------------------------------------------------

    async def record_acquiring(
        self, payload: dict, *, source_ip: str | None
    ) -> UzumCheckoutEvent:
        parsed = AcquiringCallback.model_validate(payload)
        logger.info(
            "Checkout acquiring callback: order=%s number=%s %s/%s from %s",
            parsed.order_id,
            parsed.order_number,
            parsed.operation_type,
            parsed.operation_state,
            source_ip,
        )
        event = await self._store(
            UzumCheckoutEvent(
                kind=UzumCheckoutCallbackKind.ACQUIRING,
                order_id=parsed.order_id,
                order_number=parsed.order_number,
                operation_type=parsed.operation_type,
                operation_state=parsed.operation_state,
                rrn=parsed.rrn,
                source_ip=source_ip,
                payload=payload,
            )
        )
        # The body is untrusted, so it only points at an order — the state
        # itself comes from Uzum.
        await self._verify(event)
        return event

    async def record_event(
        self, payload: dict, *, source_ip: str | None
    ) -> UzumCheckoutEvent:
        parsed = BusinessEventCallback.model_validate(payload)
        logger.info(
            "Checkout business event: order=%s number=%s %s from %s",
            parsed.order_id,
            parsed.order_number,
            parsed.event_type,
            source_ip,
        )
        return await self._store(
            UzumCheckoutEvent(
                kind=UzumCheckoutCallbackKind.EVENT,
                order_id=parsed.order_id,
                order_number=parsed.order_number,
                event_type=parsed.event_type,
                source_ip=source_ip,
                payload=payload,
            )
        )

    async def record_receipt(
        self, payload: dict, *, source_ip: str | None
    ) -> UzumCheckoutEvent:
        parsed = ReceiptCallback.model_validate(payload)
        logger.info(
            "Checkout receipt callback: order=%s %s from %s",
            parsed.order_id,
            parsed.receipt_type,
            source_ip,
        )
        return await self._store(
            UzumCheckoutEvent(
                kind=UzumCheckoutCallbackKind.RECEIPT,
                order_id=parsed.order_id,
                receipt_type=parsed.receipt_type,
                receipt_url=parsed.receipt_url,
                source_ip=source_ip,
                payload=payload,
            )
        )

    async def _store(self, event: UzumCheckoutEvent) -> UzumCheckoutEvent:
        self.db.add(event)
        await self.db.commit()
        await self.db.refresh(event)
        return event

    async def _verify(self, event: UzumCheckoutEvent) -> None:
        """Settle the order the callback named, then mark the event handled.

        Never raises: the callback must still be acknowledged with 200, or
        Uzum redelivers it up to five times. An event left unprocessed keeps
        ``processed_at = NULL`` and can be replayed later.
        """

        if not event.order_id or not settings.uzum_checkout_enabled:
            return
        try:
            payment = await self.sync_order(event.order_id)
        except UzumCheckoutApiError as exc:
            logger.warning(
                "Could not verify Checkout order %s: %s", event.order_id, exc
            )
            return
        if payment is None:
            return
        event.processed_at = datetime.now(UTC)
        await self.db.commit()

    # --- helpers -------------------------------------------------------------

    @staticmethod
    def _assert_may_pay(booking: Booking, user: User) -> None:
        if user.role == UserRole.CUSTOMER and booking.user_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not allowed to pay for this booking",
            )

    async def _assert_unpaid(self, booking: Booking) -> None:
        if booking.status == BookingStatus.CANCELLED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot pay for a cancelled booking",
            )
        settled = await self.db.scalar(
            select(Payment).where(
                Payment.booking_id == booking.id,
                Payment.status.in_((PaymentStatus.PAID, PaymentStatus.REFUND_PENDING)),
            )
        )
        if settled is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Booking is already paid"
            )

    async def _reusable_session(self, booking: Booking) -> CheckoutSessionRead | None:
        """Return the still-open Checkout session for this booking, if any.

        Registering a second order while the first form is open would let the
        guest pay twice, so a pending payment is re-checked with Uzum first: it
        is reused while Uzum still reports ``REGISTERED`` and dropped once the
        order has been declined or has expired.
        """

        pending = (
            await self.db.scalars(
                select(Payment)
                .where(
                    Payment.booking_id == booking.id,
                    Payment.method == PaymentMethod.UZUM_CHECKOUT,
                    Payment.status == PaymentStatus.PENDING,
                )
                .order_by(Payment.created_at.desc())
            )
        ).all()
        for payment in pending:
            order_id = payment.provider_payment_id
            payment_url = pick_payment_url(
                (payment.raw_payload or {}).get("register", {})
            )
            if not order_id or not payment_url:
                continue
            try:
                result = await self.client.get_order_status(order_id)
            except UzumCheckoutApiError as exc:
                logger.warning(
                    "Checkout status lookup for %s failed: %s", order_id, exc
                )
                continue
            order_status = pick_status(result)
            await self._apply(payment, order_status, result)
            if payment.status == PaymentStatus.PAID:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Booking is already paid",
                )
            if order_status == ORDER_REGISTERED:
                return CheckoutSessionRead(
                    payment_id=payment.id,
                    booking_id=booking.id,
                    order_id=order_id,
                    order_number=payment.merchant_trans_id or "",
                    payment_url=payment_url,
                    amount=payment.amount,
                    status=payment.status,
                )
        return None

    async def _payment_for_order(
        self, order_id: str, *, lock: bool = False
    ) -> Payment | None:
        stmt = select(Payment).where(
            Payment.method == PaymentMethod.UZUM_CHECKOUT,
            Payment.provider_payment_id == order_id,
        )
        if lock:
            stmt = stmt.with_for_update()
        return await self.db.scalar(stmt)

    async def _amount_uzs(self, booking: Booking) -> Decimal:
        """Booking total in so'm — Checkout only settles in UZS."""

        if booking.currency.upper() == CHECKOUT_CURRENCY:
            return booking.final_price
        converter = await ExchangeRateService(self.db).get_converter(CHECKOUT_CURRENCY)
        amount = converter.convert(
            booking.final_price, booking.currency, CHECKOUT_CURRENCY
        )
        if amount is None:
            logger.error(
                "No %s_UZS exchange rate; cannot price booking %s for Checkout",
                booking.currency,
                booking.code,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Missing {booking.currency}_UZS exchange rate",
            )
        return amount

    async def _payment_details(self, booking: Booking) -> str:
        name = await sanatorium_name_for_booking(self.db, booking)
        stay = f"{booking.check_in.isoformat()} — {booking.check_out.isoformat()}"
        return f"UzWellness {booking.code}: {name or 'booking'} ({stay})"

    @staticmethod
    def _cart(
        payment_id: uuid.UUID, booking: Booking, amount_tiyin: int, title: str
    ) -> dict | None:
        """Fiscalization cart, or ``None`` when the terminal does not need one.

        Uzum validates ``spic``/``packageCode`` against the national product
        catalogue (tasnif.soliq.uz) and rejects registration with 3055 if they
        do not match, so they are configuration, not literals.
        """

        if not settings.UZUM_CHECKOUT_AUTOFISCALIZATION:
            return None
        return {
            "cartId": str(payment_id),
            # Uzum rejects a cart carrying receiptParams without a receiptType.
            "receiptType": "PURCHASE",
            "total": amount_tiyin,
            "items": [
                {
                    "productId": str(booking.id),
                    # Uzum caps a cart item's title at 63 characters.
                    "title": title[:63],
                    "quantity": 1,
                    "unitPrice": amount_tiyin,
                    "total": amount_tiyin,
                    "receiptParams": {
                        "spic": settings.UZUM_CHECKOUT_SPIC,
                        "packageCode": settings.UZUM_CHECKOUT_PACKAGE_CODE,
                        "vatPercent": settings.UZUM_CHECKOUT_VAT_PERCENT,
                        "TIN": settings.UZUM_CHECKOUT_TIN,
                    },
                }
            ],
        }


def _order_number(booking: Booking, payment_id: uuid.UUID) -> str:
    """Merchant-side order id, ≤36 chars and unique per attempt.

    Uzum rejects a repeated ``orderNumber`` with 3027, so the reservation
    number alone would block a second attempt after an abandoned form.
    """

    return f"{booking.reservation_number}-{payment_id.hex[:8]}"[:36]


def get_uzum_checkout_service(
    db: AsyncSession = Depends(get_db),
) -> UzumCheckoutService:
    return UzumCheckoutService(db)
