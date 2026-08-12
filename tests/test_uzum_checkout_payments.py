"""Uzum Checkout — registering a card payment and settling it afterwards.

The callback side (recording and acknowledgement) lives in
``test_uzum_checkout_callbacks.py``; here Uzum is a stub client so the tests
cover what we send, what we store, and how an order state moves a booking.
"""

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.integrations.uzum.checkout import UzumCheckoutApiError
from app.models.booking import Booking, BookingStatus, BookingType
from app.models.payment import Payment, PaymentMethod, PaymentStatus
from app.models.user import User
from app.services.uzum_checkout_service import UzumCheckoutService
from tests.factories import make_exchange_rate, make_room, make_sanatorium, make_user

ORDER_ID = "b3e1eced-f2bd-4d8c-9765-fbc9d1d222d5"
PAY_URL = "https://test-checkout.uzumbank.uz/pay/b3e1eced"


class StubCheckout:
    """Stands in for Uzum: records calls, replays scripted results."""

    def __init__(self, *, register: dict | None = None, status: str = "REGISTERED"):
        self.register_calls: list[dict[str, Any]] = []
        self.status_calls: list[str] = []
        self._register = (
            register
            if register is not None
            else {"orderId": ORDER_ID, "paymentRedirectUrl": PAY_URL}
        )
        self.status = status
        self.register_error: UzumCheckoutApiError | None = None

    async def register(self, **kwargs: Any) -> dict:
        self.register_calls.append(kwargs)
        if self.register_error is not None:
            raise self.register_error
        return self._register

    async def get_order_status(self, order_id: str) -> dict:
        self.status_calls.append(order_id)
        return {"orderId": order_id, "status": self.status}


@pytest.fixture(autouse=True)
def checkout_credentials(monkeypatch: pytest.MonkeyPatch):
    """Checkout is off by default; these tests need it configured."""

    monkeypatch.setattr(settings, "UZUM_CHECKOUT_TERMINAL_ID", "terminal-id")
    monkeypatch.setattr(settings, "UZUM_CHECKOUT_API_KEY", "api-key")
    monkeypatch.setattr(settings, "UZUM_CHECKOUT_AUTOFISCALIZATION", False)


async def _booking(
    db: AsyncSession,
    owner: User,
    *,
    price: Decimal = Decimal("1200000.00"),
    currency: str = "UZS",
) -> Booking:
    sanatorium = await make_sanatorium(db)
    room = await make_room(db, sanatorium=sanatorium)
    booking = Booking(
        user_id=owner.id,
        room_id=room.id,
        booking_type=BookingType.ROOM,
        check_in=date.today() + timedelta(days=10),
        check_out=date.today() + timedelta(days=12),
        guests=1,
        status=BookingStatus.PENDING,
        final_price=price,
        currency=currency,
    )
    db.add(booking)
    await db.commit()
    await db.refresh(booking)
    return booking


class TestRegister:
    async def test_registers_order_and_stores_payment(self, db: AsyncSession):
        owner = await make_user(db, email="checkout-1@test.com")
        booking = await _booking(db, owner)
        stub = StubCheckout()

        session = await UzumCheckoutService(db, stub).start(booking.id, owner)

        assert session.payment_url == PAY_URL
        assert session.order_id == ORDER_ID
        # Amount is sent in tiyin, and only in tiyin.
        assert stub.register_calls[0]["amount_tiyin"] == 120_000_000
        # orderNumber stays unique per attempt (Uzum rejects repeats with 3027).
        assert stub.register_calls[0]["order_number"].startswith(
            booking.reservation_number
        )
        assert stub.register_calls[0]["order_number"] != booking.reservation_number

        payment = await db.get(Payment, session.payment_id)
        assert payment is not None
        assert payment.method == PaymentMethod.UZUM_CHECKOUT
        assert payment.status == PaymentStatus.PENDING
        assert payment.provider_payment_id == ORDER_ID
        assert payment.currency == "UZS"
        assert payment.amount == Decimal("1200000.00")

    async def test_converts_foreign_currency_to_uzs(self, db: AsyncSession):
        owner = await make_user(db, email="checkout-2@test.com")
        booking = await _booking(db, owner, price=Decimal("100.00"), currency="USD")
        await make_exchange_rate(db, pair="USD_UZS", rate="12500")
        stub = StubCheckout()

        session = await UzumCheckoutService(db, stub).start(booking.id, owner)

        assert session.amount == Decimal("1250000.00")
        assert stub.register_calls[0]["amount_tiyin"] == 125_000_000

    async def test_sends_fiscalization_cart_when_enabled(
        self, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(settings, "UZUM_CHECKOUT_AUTOFISCALIZATION", True)
        monkeypatch.setattr(settings, "UZUM_CHECKOUT_SPIC", "10112001001000000")
        monkeypatch.setattr(settings, "UZUM_CHECKOUT_PACKAGE_CODE", "1513583")
        monkeypatch.setattr(settings, "UZUM_CHECKOUT_TIN", "123456789")
        owner = await make_user(db, email="checkout-3@test.com")
        booking = await _booking(db, owner)
        stub = StubCheckout()

        await UzumCheckoutService(db, stub).start(booking.id, owner)

        cart = stub.register_calls[0]["cart"]
        assert cart["total"] == 120_000_000
        # Uzum rejects receiptParams without a receiptType on the cart.
        assert cart["receiptType"] == "PURCHASE"
        item = cart["items"][0]
        assert item["total"] == 120_000_000
        assert item["receiptParams"] == {
            "spic": "10112001001000000",
            "packageCode": "1513583",
            "vatPercent": 0,
            "TIN": "123456789",
        }

    async def test_no_cart_when_autofiscalization_is_off(self, db: AsyncSession):
        owner = await make_user(db, email="checkout-4@test.com")
        booking = await _booking(db, owner)
        stub = StubCheckout()

        await UzumCheckoutService(db, stub).start(booking.id, owner)

        assert stub.register_calls[0]["cart"] is None

    async def test_uzum_error_is_reported_as_bad_gateway(self, db: AsyncSession):
        owner = await make_user(db, email="checkout-5@test.com")
        booking = await _booking(db, owner)
        stub = StubCheckout()
        stub.register_error = UzumCheckoutApiError("cart is invalid", code=3055)

        with pytest.raises(HTTPException) as exc:
            await UzumCheckoutService(db, stub).start(booking.id, owner)

        assert exc.value.status_code == 502
        # A failed registration must not leave a payment row behind.
        assert (await db.scalars(select(Payment))).all() == []

    async def test_missing_payment_url_is_not_persisted(self, db: AsyncSession):
        owner = await make_user(db, email="checkout-6@test.com")
        booking = await _booking(db, owner)
        stub = StubCheckout(register={"orderId": ORDER_ID})

        with pytest.raises(HTTPException) as exc:
            await UzumCheckoutService(db, stub).start(booking.id, owner)

        assert exc.value.status_code == 502

    async def test_second_attempt_reuses_the_open_form(self, db: AsyncSession):
        owner = await make_user(db, email="checkout-7@test.com")
        booking = await _booking(db, owner)
        stub = StubCheckout()
        service = UzumCheckoutService(db, stub)

        first = await service.start(booking.id, owner)
        second = await service.start(booking.id, owner)

        assert second.payment_id == first.payment_id
        assert len(stub.register_calls) == 1
        assert stub.status_calls == [ORDER_ID]

    async def test_paid_booking_cannot_be_paid_again(self, db: AsyncSession):
        owner = await make_user(db, email="checkout-8@test.com")
        booking = await _booking(db, owner)
        db.add(
            Payment(
                booking_id=booking.id,
                method=PaymentMethod.CASH,
                status=PaymentStatus.PAID,
                amount=Decimal("1200000.00"),
                currency="UZS",
            )
        )
        await db.commit()

        with pytest.raises(HTTPException) as exc:
            await UzumCheckoutService(db, StubCheckout()).start(booking.id, owner)

        assert exc.value.status_code == 409

    async def test_other_customers_booking_is_forbidden(self, db: AsyncSession):
        owner = await make_user(db, email="checkout-9@test.com")
        intruder = await make_user(db, email="checkout-10@test.com")
        booking = await _booking(db, owner)

        with pytest.raises(HTTPException) as exc:
            await UzumCheckoutService(db, StubCheckout()).start(booking.id, intruder)

        assert exc.value.status_code == 403

    async def test_disabled_integration_answers_503(
        self, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(settings, "UZUM_CHECKOUT_API_KEY", "")
        owner = await make_user(db, email="checkout-11@test.com")
        booking = await _booking(db, owner)

        with pytest.raises(HTTPException) as exc:
            await UzumCheckoutService(db, StubCheckout()).start(booking.id, owner)

        assert exc.value.status_code == 503


class TestSettlement:
    async def test_completed_order_pays_and_confirms(self, db: AsyncSession):
        owner = await make_user(db, email="settle-1@test.com")
        booking = await _booking(db, owner)
        stub = StubCheckout()
        service = UzumCheckoutService(db, stub)
        session = await service.start(booking.id, owner)

        stub.status = "COMPLETED"
        await service.sync_order(ORDER_ID)

        payment = await db.get(Payment, session.payment_id)
        await db.refresh(booking)
        assert payment is not None
        assert payment.status == PaymentStatus.PAID
        assert payment.paid_at is not None
        assert booking.status == BookingStatus.CONFIRMED

    async def test_declined_order_fails_the_payment(self, db: AsyncSession):
        owner = await make_user(db, email="settle-2@test.com")
        booking = await _booking(db, owner)
        stub = StubCheckout()
        service = UzumCheckoutService(db, stub)
        session = await service.start(booking.id, owner)

        stub.status = "DECLINED"
        await service.sync_order(ORDER_ID)

        payment = await db.get(Payment, session.payment_id)
        await db.refresh(booking)
        assert payment is not None
        assert payment.status == PaymentStatus.FAILED
        # A declined card leaves the booking where it was.
        assert booking.status == BookingStatus.PENDING

    async def test_refunded_order_marks_the_payment_refunded(self, db: AsyncSession):
        owner = await make_user(db, email="settle-3@test.com")
        booking = await _booking(db, owner)
        stub = StubCheckout()
        service = UzumCheckoutService(db, stub)
        session = await service.start(booking.id, owner)

        stub.status = "REFUNDED"
        await service.sync_order(ORDER_ID)

        payment = await db.get(Payment, session.payment_id)
        assert payment is not None
        assert payment.status == PaymentStatus.REFUNDED
        assert payment.cancelled_at is not None

    async def test_unknown_order_is_ignored(self, db: AsyncSession):
        assert await UzumCheckoutService(db, StubCheckout()).sync_order("nope") is None


class TestCallbackVerification:
    async def test_acquiring_callback_settles_through_the_api(self, db: AsyncSession):
        owner = await make_user(db, email="verify-1@test.com")
        booking = await _booking(db, owner)
        stub = StubCheckout()
        service = UzumCheckoutService(db, stub)
        session = await service.start(booking.id, owner)

        stub.status = "COMPLETED"
        event = await service.record_acquiring(
            {
                "orderId": ORDER_ID,
                "operationType": "COMPLETE",
                # A body claiming success proves nothing; the state below comes
                # from getOrderStatus, which the stub answers separately.
                "operationState": "SUCCESS",
            },
            source_ip="1.2.3.4",
        )

        assert event.processed_at is not None
        payment = await db.get(Payment, session.payment_id)
        assert payment is not None
        assert payment.status == PaymentStatus.PAID

    async def test_callback_body_alone_never_pays(self, db: AsyncSession):
        owner = await make_user(db, email="verify-2@test.com")
        booking = await _booking(db, owner)
        stub = StubCheckout()  # Uzum still reports REGISTERED
        service = UzumCheckoutService(db, stub)
        session = await service.start(booking.id, owner)

        await service.record_acquiring(
            {
                "orderId": ORDER_ID,
                "operationType": "COMPLETE",
                "operationState": "SUCCESS",
            },
            source_ip=None,
        )

        payment = await db.get(Payment, session.payment_id)
        assert payment is not None
        assert payment.status == PaymentStatus.PENDING

    async def test_unverifiable_callback_stays_unprocessed(self, db: AsyncSession):
        service = UzumCheckoutService(db, StubCheckout())

        event = await service.record_acquiring(
            {"orderId": "unknown-order", "operationType": "COMPLETE"}, source_ip=None
        )

        assert event.processed_at is None


class TestResultParsing:
    """Uzum documents the register result only as ``{...}``."""

    async def test_alternate_url_key_is_accepted(self, db: AsyncSession):
        owner = await make_user(db, email="parse-1@test.com")
        booking = await _booking(db, owner)
        # Older Uzum examples call it paymentUrl; the sandbox says
        # paymentRedirectUrl. Both must resolve to the same session.
        stub = StubCheckout(register={"orderId": ORDER_ID, "paymentUrl": PAY_URL})

        session = await UzumCheckoutService(db, stub).start(booking.id, owner)

        assert session.payment_url == PAY_URL


class TestSettingsHygiene:
    """`.env` is hand-edited on the server; a stray comment must not ship."""

    def test_inline_comment_is_stripped_from_fiscal_codes(self):
        from app.core.config import Settings

        parsed = Settings(
            DATABASE_URL="postgresql+asyncpg://u:p@localhost/db",
            REDIS_URL="redis://localhost:6379/0",
            JWT_SECRET_KEY="x" * 32,
            # dotenv only strips `#` when a space precedes it, so this is
            # exactly what reached Uzum from the VPS and was rejected.
            UZUM_CHECKOUT_SPIC="10204001001000000# Гостиничные услуги",
            UZUM_CHECKOUT_PACKAGE_CODE="1495084   # услуга (раз)",
            UZUM_CHECKOUT_TIN=" 300717633 ",
        )

        assert parsed.UZUM_CHECKOUT_SPIC == "10204001001000000"
        assert parsed.UZUM_CHECKOUT_PACKAGE_CODE == "1495084"
        assert parsed.UZUM_CHECKOUT_TIN == "300717633"


class TestPaymentDescription:
    """The "Description" line above the card form — the guest's only receipt
    of what they are about to pay for."""

    async def test_names_property_room_dates_and_party(self, db: AsyncSession):
        owner = await make_user(db, email="desc-1@test.com")
        booking = await _booking(db, owner)
        stub = StubCheckout()

        await UzumCheckoutService(db, stub).start(booking.id, owner, locale="uz")

        details = stub.register_calls[0]["payment_details"]
        assert "2 kecha" in details
        assert "1 mehmon" in details
        assert f"Bron {booking.code}" in details
        assert booking.check_in.strftime("%d.%m.%Y") in details

    async def test_follows_the_form_language(self, db: AsyncSession):
        owner = await make_user(db, email="desc-2@test.com")
        booking = await _booking(db, owner)
        stub = StubCheckout()

        await UzumCheckoutService(db, stub).start(booking.id, owner, locale="ru")

        details = stub.register_calls[0]["payment_details"]
        assert "ноч." in details
        assert "Бронь" in details

    async def test_cart_title_stays_within_uzum_limit(self, db: AsyncSession):
        owner = await make_user(db, email="desc-3@test.com")
        booking = await _booking(db, owner)
        stub = StubCheckout()

        service = UzumCheckoutService(db, stub)
        title = await service._cart_title(booking, "uz")

        # Uzum rejects a cart item title longer than 63 characters with 2000.
        assert len(title) <= 63
        assert booking.code in title
