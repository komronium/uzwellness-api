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
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.ids import uuid7
from app.core.sanatorium_lookup import sanatorium_name_for_booking
from app.core.utils import pick_locale
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
from app.models.booking import Booking, BookingStatus, BookingType
from app.models.payment import Payment, PaymentMethod, PaymentStatus
from app.models.program import TreatmentProgram
from app.models.room import Room
from app.models.user import User, UserRole
from app.core.errors import missing_exchange_rate
from app.services.booking_visibility import admin_owns_booking_sanatorium
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
                detail=(
                    "Card payment is not available right now. "
                    "Please pay at the property or contact "
                    "info@uzwellness.com."
                ),
            )

        booking = await self.db.scalar(
            select(Booking).where(Booking.id == booking_id).with_for_update()
        )
        if booking is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No booking found with this id under your account",
            )
        await self._assert_may_pay(booking, user)
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
                detail=(
                    "This booking has nothing left to pay online. "
                    "Please contact info@uzwellness.com if that looks wrong."
                ),
            )

        payment_id = uuid7()
        order_number = _order_number(booking, payment_id)
        details = await self._payment_details(booking, locale)
        # The fiscal receipt line is its own thing: capped at 63 characters, so
        # it names the property and the booking rather than the whole stay.
        cart_title = await self._cart_title(booking, locale)
        cart = self._cart(payment_id, booking, amount_tiyin, cart_title)

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
            # exc.message is Uzum's own Russian/English operator text; the
            # guest gets a sentence they can act on and the code for support.
            reference = f" (Uzum code {exc.code})" if exc.code is not None else ""
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=(
                    "Uzum Bank could not open the payment form for this "
                    f"booking{reference}. Please try again in a minute, or pay "
                    "at the property."
                ),
            ) from exc

        order_id = pick_order_id(result)
        payment_url = pick_payment_url(result)
        if not order_id or not payment_url:
            logger.error("Uzum Checkout register returned %s", result)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=(
                    "Uzum Bank did not return a payment page for this booking. "
                    "Please try again in a minute, or pay at the property."
                ),
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
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No payment found with this id",
            )
        booking = await self.db.get(Booking, payment.booking_id)
        if booking is not None:
            await self._assert_may_pay(booking, user)
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
        booking = await self.db.get(Booking, payment.booking_id)

        confirmed = False
        if order_status == ORDER_COMPLETED and not self._amount_matches(
            payment, result
        ):
            # Uzum settled a different sum than the one we registered, so we
            # do not know what this booking is owed. Leaving the payment where
            # it is (pending) keeps the stay unconfirmed and keeps the row in
            # every "needs attention" list, which is the honest answer; marking
            # it paid would tell the property money arrived that may not have.
            logger.error(
                "Uzum Checkout order %s settled an unexpected amount; payment "
                "%s left %s for manual review",
                payment.provider_payment_id,
                payment.id,
                payment.status,
            )
        elif order_status == ORDER_COMPLETED:
            if booking is not None and booking.status == BookingStatus.CANCELLED:
                # The form stays open after a cancellation and Uzum has no way
                # to withdraw an order, so the guest can still pay for a stay
                # that no longer exists. The money did arrive — book it as owed
                # back rather than as a settled payment, which is what the
                # cancellation path would have done had it arrived first.
                if payment.status != PaymentStatus.REFUND_PENDING:
                    payment.status = PaymentStatus.REFUND_PENDING
                    payment.paid_at = payment.paid_at or datetime.now(UTC)
                    logger.error(
                        "Uzum Checkout order %s paid after booking %s was "
                        "cancelled — refund owed",
                        payment.provider_payment_id,
                        booking.code,
                    )
            elif payment.status != PaymentStatus.PAID:
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

        if (
            confirmed
            and booking is not None
            and booking.status == BookingStatus.PENDING
        ):
            booking.status = BookingStatus.CONFIRMED
        await self.db.commit()
        if confirmed and booking is not None:
            await send_booking_confirmed_email(self.db, booking)

    @staticmethod
    def _amount_matches(payment: Payment, result: dict) -> bool:
        """Whether Uzum settled exactly the sum we registered.

        ``completedAmount`` is what actually left the card, in tiyin. A gap
        means a partial refund happened outside this flow, or the order does
        not belong to this payment — either way the booking must not be
        treated as paid on it.

        Uzum does not always send the field; when it is absent there is
        nothing to disagree with, so the order is taken at its word.
        """

        completed = result.get("completedAmount")
        if not isinstance(completed, int):
            return True
        expected = int((payment.amount * _TIYIN).to_integral_value(ROUND_HALF_UP))
        if completed == expected:
            return True
        logger.error(
            "Uzum Checkout order %s settled %s tiyin, expected %s (payment %s)",
            payment.provider_payment_id,
            completed,
            expected,
            payment.id,
        )
        return False

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

    async def _assert_may_pay(self, booking: Booking, user: User) -> None:
        """Only the guest who booked, their property's admin, or the platform.

        Checking the customer role alone left agents and the transfer operator
        able to open a Checkout form against any booking id.
        """

        if user.role == UserRole.SUPER_ADMIN:
            return
        if user.role == UserRole.ADMIN and await admin_owns_booking_sanatorium(
            self.db, booking, user.id
        ):
            return
        if booking.user_id is not None and booking.user_id == user.id:
            return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This booking belongs to another account.",
        )

    async def _assert_unpaid(self, booking: Booking) -> None:
        if booking.status == BookingStatus.CANCELLED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "This booking was cancelled, so it cannot be paid. "
                    "Please make a new booking."
                ),
            )
        settled = await self.db.scalar(
            select(Payment).where(
                Payment.booking_id == booking.id,
                Payment.status.in_((PaymentStatus.PAID, PaymentStatus.REFUND_PENDING)),
            )
        )
        if settled is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This booking has already been paid in full.",
            )
        await self._assert_no_merchant_transaction(booking)

    async def _assert_no_merchant_transaction(self, booking: Booking) -> None:
        """Refuse a card form while the guest is mid-payment in the Uzum app.

        Checkout and the Merchant API are separate Uzum products that settle
        independently, so a guest holding an open transaction in one and a
        form in the other can be charged twice for the same stay. Only a
        *live* transaction blocks: Uzum abandons an unconfirmed one after
        ``UZUM_TRANSACTION_TIMEOUT_MINUTES``, and a stale row must not lock
        the booking out of paying at all.
        """

        cutoff = datetime.now(UTC) - timedelta(
            minutes=settings.UZUM_TRANSACTION_TIMEOUT_MINUTES
        )
        in_flight = await self.db.scalar(
            select(Payment).where(
                Payment.booking_id == booking.id,
                Payment.method == PaymentMethod.UZUM,
                Payment.status == PaymentStatus.PENDING,
                Payment.created_at >= cutoff,
            )
        )
        if in_flight is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "A payment for this booking is already open in the Uzum "
                    "Bank app. Finish it there, or wait a few minutes and try "
                    "again."
                ),
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
                    detail="This booking has already been paid in full.",
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
            raise missing_exchange_rate(booking.currency, CHECKOUT_CURRENCY)
        return amount

    async def _payment_details(self, booking: Booking, locale: str | None) -> str:
        """The "Description" line the guest reads above the card form.

        This is the only place where they can check *what* they are paying
        for, so it names the property, the room or programme, the dates and
        the party size — in the same language as the form itself.
        """

        lang = _details_locale(locale)
        words = _DETAIL_WORDS[lang]
        parts: list[str] = []

        property_name = await sanatorium_name_for_booking(self.db, booking, lang)
        item_name = await self._booked_item_name(booking, lang)
        headline = " — ".join(p for p in (property_name, item_name) if p)
        if headline:
            parts.append(headline)

        if booking.booking_type == BookingType.ROOM:
            nights = (booking.check_out - booking.check_in).days
            parts.append(
                f"{_short_date(booking.check_in)}–{_short_date(booking.check_out)}"
            )
            if nights > 0:
                parts.append(f"{nights} {words['nights']}")
            if booking.rooms_count > 1:
                parts.append(f"{booking.rooms_count} {words['rooms']}")
        else:
            parts.append(_short_date(booking.check_in))

        parts.append(f"{booking.guests} {words['guests']}")
        parts.append(f"{words['booking']} {booking.code}")
        return " · ".join(parts)

    async def _cart_title(self, booking: Booking, locale: str | None) -> str:
        lang = _details_locale(locale)
        name = await sanatorium_name_for_booking(self.db, booking, lang)
        title = f"{name} · {booking.code}" if name else f"UzWellness {booking.code}"
        return title[:63]

    async def _booked_item_name(self, booking: Booking, locale: str) -> str:
        """Room category or programme name, whichever the booking points at."""

        if booking.room_id is not None:
            name = await self.db.scalar(
                select(Room.name).where(Room.id == booking.room_id)
            )
        elif booking.program_id is not None:
            name = await self.db.scalar(
                select(TreatmentProgram.name).where(
                    TreatmentProgram.id == booking.program_id
                )
            )
        else:
            return ""
        return pick_locale(name, locale) if name else ""

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


_DETAIL_WORDS = {
    "uz": {
        "nights": "kecha",
        "guests": "mehmon",
        "rooms": "xona",
        "booking": "Bron",
    },
    "ru": {
        "nights": "ноч.",
        "guests": "гост.",
        "rooms": "номер(а)",
        "booking": "Бронь",
    },
    "en": {
        "nights": "nights",
        "guests": "guests",
        "rooms": "rooms",
        "booking": "Booking",
    },
}


def _details_locale(locale: str | None) -> str:
    lang = (locale or "").lower()[:2]
    return lang if lang in _DETAIL_WORDS else "en"


def _short_date(value: date) -> str:
    return value.strftime("%d.%m.%Y")


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
