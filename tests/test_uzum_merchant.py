"""Uzum Bank Merchant API webhooks — the five calls Uzum makes into us.

The customer pays inside the Uzum app, so every test here drives the API the
way Uzum does: HTTP POST, Basic auth, camelCase JSON, tiyin amounts.
"""

from __future__ import annotations

import base64
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.booking import Booking, BookingStatus, BookingType
from app.models.payment import Payment, PaymentMethod, PaymentStatus
from tests.factories import make_exchange_rate, make_room, make_sanatorium, make_user

SERVICE_ID = 123123
USERNAME = "uzwellness"
PASSWORD = "s3cret-pass"

# 100.00 USD at 12 500 UZS = 1 250 000 UZS = 125 000 000 tiyin
EXPECTED_TIYIN = 125_000_000

BASE = "/api/payments/uzum"


def auth_headers(user: str = USERNAME, password: str = PASSWORD) -> dict[str, str]:
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


@pytest.fixture(autouse=True)
def uzum_settings():
    saved = (
        settings.UZUM_SERVICE_ID,
        settings.UZUM_MERCHANT_USERNAME,
        settings.UZUM_MERCHANT_PASSWORD,
        settings.UZUM_TRANSACTION_TIMEOUT_MINUTES,
    )
    settings.UZUM_SERVICE_ID = SERVICE_ID
    settings.UZUM_MERCHANT_USERNAME = USERNAME
    settings.UZUM_MERCHANT_PASSWORD = PASSWORD
    settings.UZUM_TRANSACTION_TIMEOUT_MINUTES = 30
    yield
    (
        settings.UZUM_SERVICE_ID,
        settings.UZUM_MERCHANT_USERNAME,
        settings.UZUM_MERCHANT_PASSWORD,
        settings.UZUM_TRANSACTION_TIMEOUT_MINUTES,
    ) = saved


async def make_booking(
    db: AsyncSession,
    *,
    email: str = "guest@test.com",
    status: BookingStatus = BookingStatus.PENDING,
    price: str = "100.00",
    currency: str = "USD",
) -> Booking:
    await make_exchange_rate(db)
    user = await make_user(db, email=email)
    sanatorium = await make_sanatorium(db)
    room = await make_room(db, sanatorium=sanatorium)
    booking = Booking(
        user_id=user.id,
        room_id=room.id,
        booking_type=BookingType.ROOM,
        check_in=date.today() + timedelta(days=10),
        check_out=date.today() + timedelta(days=12),
        guests=1,
        status=status,
        final_price=Decimal(price),
        currency=currency,
    )
    db.add(booking)
    await db.commit()
    await db.refresh(booking)
    return booking


def check_body(order_id: str, **overrides) -> dict:
    body = {
        "serviceId": SERVICE_ID,
        "timestamp": 1698361456728,
        "params": {"order_id": order_id},
    }
    return {**body, **overrides}


def create_body(order_id: str, trans_id: str, amount: int = EXPECTED_TIYIN) -> dict:
    return {
        "serviceId": SERVICE_ID,
        "timestamp": 1698361456728,
        "transId": trans_id,
        "params": {"order_id": order_id},
        "amount": amount,
    }


def confirm_body(trans_id: str) -> dict:
    return {
        "serviceId": SERVICE_ID,
        "timestamp": 1698361456728,
        "transId": trans_id,
        "paymentSource": "UZCARD",
        "phone": "998901234567",
        "cardType": 2,
    }


def trans_body(trans_id: str) -> dict:
    return {
        "serviceId": SERVICE_ID,
        "timestamp": 1698361456728,
        "transId": trans_id,
    }


async def open_transaction(
    client: AsyncClient, booking: Booking, trans_id: str | None = None
) -> str:
    trans_id = trans_id or str(uuid.uuid4())
    resp = await client.post(
        f"{BASE}/create",
        json=create_body(booking.reservation_number, trans_id),
        headers=auth_headers(),
    )
    assert resp.status_code == 200, resp.text
    return trans_id


# --- authorization -----------------------------------------------------------


class TestAuthorization:
    async def test_missing_header_is_access_denied(
        self, client: AsyncClient, db: AsyncSession
    ):
        booking = await make_booking(db)
        resp = await client.post(
            f"{BASE}/check", json=check_body(booking.reservation_number)
        )
        assert resp.status_code == 400
        assert resp.json()["errorCode"] == "10001"
        assert resp.json()["status"] == "FAILED"

    async def test_wrong_password_is_access_denied(
        self, client: AsyncClient, db: AsyncSession
    ):
        booking = await make_booking(db)
        resp = await client.post(
            f"{BASE}/check",
            json=check_body(booking.reservation_number),
            headers=auth_headers(password="wrong"),
        )
        assert resp.status_code == 400
        assert resp.json()["errorCode"] == "10001"

    async def test_unconfigured_credentials_reject_everything(
        self, client: AsyncClient, db: AsyncSession
    ):
        booking = await make_booking(db)
        settings.UZUM_MERCHANT_PASSWORD = ""
        resp = await client.post(
            f"{BASE}/check",
            json=check_body(booking.reservation_number),
            headers=auth_headers(),
        )
        assert resp.status_code == 400
        assert resp.json()["errorCode"] == "10001"

    async def test_unknown_service_id_is_rejected(
        self, client: AsyncClient, db: AsyncSession
    ):
        booking = await make_booking(db)
        resp = await client.post(
            f"{BASE}/check",
            json=check_body(booking.reservation_number, serviceId=999),
            headers=auth_headers(),
        )
        assert resp.status_code == 400
        assert resp.json()["errorCode"] == "10006"


# --- request format ----------------------------------------------------------


class TestRequestFormat:
    async def test_malformed_json_is_parse_error(self, client: AsyncClient):
        resp = await client.post(
            f"{BASE}/check",
            content=b"{not json",
            headers={**auth_headers(), "Content-Type": "application/json"},
        )
        assert resp.status_code == 400
        assert resp.json()["errorCode"] == "10002"

    async def test_missing_field_is_missing_parameters(self, client: AsyncClient):
        resp = await client.post(
            f"{BASE}/create",
            json={"serviceId": SERVICE_ID, "timestamp": 1, "params": {}},
            headers=auth_headers(),
        )
        assert resp.status_code == 400
        assert resp.json()["errorCode"] == "10005"

    async def test_params_without_order_id_is_missing_parameters(
        self, client: AsyncClient
    ):
        resp = await client.post(
            f"{BASE}/check",
            json={"serviceId": SERVICE_ID, "timestamp": 1, "params": {}},
            headers=auth_headers(),
        )
        assert resp.status_code == 400
        assert resp.json()["errorCode"] == "10005"

    async def test_wrong_http_method_is_invalid_operation(self, client: AsyncClient):
        resp = await client.get(f"{BASE}/check", headers=auth_headers())
        assert resp.status_code == 400
        assert resp.json()["errorCode"] == "10003"

    async def test_check_error_envelope_has_no_trans_id(self, client: AsyncClient):
        resp = await client.post(
            f"{BASE}/check",
            json=check_body("nope"),
            headers=auth_headers(),
        )
        body = resp.json()
        assert "transId" not in body
        assert body["serviceId"] == SERVICE_ID
        assert isinstance(body["timestamp"], int)


# --- /check ------------------------------------------------------------------


class TestCheck:
    async def test_known_reservation_number_is_ok(
        self, client: AsyncClient, db: AsyncSession
    ):
        booking = await make_booking(db)
        resp = await client.post(
            f"{BASE}/check",
            json=check_body(booking.reservation_number),
            headers=auth_headers(),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "OK"
        assert body["serviceId"] == SERVICE_ID
        # Uzum's payment form pre-fills and locks `data.amount`, which is in
        # so'm — unlike every wire `amount` field, which is in tiyin.
        assert body["data"]["amount"]["value"] == "1250000"
        assert "order_id" not in body["data"]
        assert body["data"]["property"]["value"] == "Test Sanatorium"

    async def test_booking_code_also_resolves(
        self, client: AsyncClient, db: AsyncSession
    ):
        booking = await make_booking(db)
        resp = await client.post(
            f"{BASE}/check",
            json=check_body(booking.code),
            headers=auth_headers(),
        )
        assert resp.status_code == 200, resp.text

    @pytest.mark.parametrize("key", ["orderId", "account", "user_id", "code"])
    async def test_alternative_param_keys_resolve(
        self, client: AsyncClient, db: AsyncSession, key: str
    ):
        """Uzum's field name must not decide whether a payment can happen."""

        booking = await make_booking(db, email=f"alias-{key}@test.com")
        resp = await client.post(
            f"{BASE}/check",
            json={
                "serviceId": SERVICE_ID,
                "timestamp": 1698361456728,
                "params": {key: booking.reservation_number},
            },
            headers=auth_headers(),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "OK"

    async def test_unknown_order_id_is_account_not_found(self, client: AsyncClient):
        resp = await client.post(
            f"{BASE}/check", json=check_body("0000000000000000"), headers=auth_headers()
        )
        assert resp.status_code == 400
        assert resp.json()["errorCode"] == "10007"

    async def test_cancelled_booking_is_payment_cancelled(
        self, client: AsyncClient, db: AsyncSession
    ):
        booking = await make_booking(db, status=BookingStatus.CANCELLED)
        resp = await client.post(
            f"{BASE}/check",
            json=check_body(booking.reservation_number),
            headers=auth_headers(),
        )
        assert resp.status_code == 400
        assert resp.json()["errorCode"] == "10009"

    async def test_paid_booking_is_already_paid(
        self, client: AsyncClient, db: AsyncSession
    ):
        booking = await make_booking(db)
        db.add(
            Payment(
                booking_id=booking.id,
                method=PaymentMethod.CASH,
                status=PaymentStatus.PAID,
                amount=Decimal("100.00"),
                currency="USD",
            )
        )
        await db.commit()
        resp = await client.post(
            f"{BASE}/check",
            json=check_body(booking.reservation_number),
            headers=auth_headers(),
        )
        assert resp.status_code == 400
        assert resp.json()["errorCode"] == "10008"


# --- /create -----------------------------------------------------------------


class TestCreate:
    async def test_creates_pending_payment_in_uzs(
        self, client: AsyncClient, db: AsyncSession
    ):
        booking = await make_booking(db)
        trans_id = str(uuid.uuid4())

        resp = await client.post(
            f"{BASE}/create",
            json=create_body(booking.reservation_number, trans_id),
            headers=auth_headers(),
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "CREATED"
        assert body["transId"] == trans_id
        assert body["amount"] == EXPECTED_TIYIN
        assert isinstance(body["transTime"], int)
        # The displayed figure must always be the charged one, /100.
        assert int(body["data"]["amount"]["value"]) * 100 == body["amount"]

        payment = await db.scalar(
            select(Payment).where(Payment.provider_payment_id == trans_id)
        )
        assert payment is not None
        assert payment.method == PaymentMethod.UZUM
        assert payment.status == PaymentStatus.PENDING
        assert payment.amount == Decimal("1250000.00")
        assert payment.currency == "UZS"
        assert payment.merchant_trans_id == booking.reservation_number

    async def test_uzs_booking_needs_no_conversion(
        self, client: AsyncClient, db: AsyncSession
    ):
        booking = await make_booking(db, price="1500000.00", currency="UZS")
        resp = await client.post(
            f"{BASE}/create",
            json=create_body(
                booking.reservation_number, str(uuid.uuid4()), amount=150_000_000
            ),
            headers=auth_headers(),
        )
        assert resp.status_code == 200, resp.text

    async def test_wrong_amount_is_rejected(
        self, client: AsyncClient, db: AsyncSession
    ):
        booking = await make_booking(db)
        resp = await client.post(
            f"{BASE}/create",
            json=create_body(booking.reservation_number, str(uuid.uuid4()), amount=1),
            headers=auth_headers(),
        )
        assert resp.status_code == 400
        assert resp.json()["errorCode"] == "10011"
        assert resp.json()["transId"] is not None

    async def test_pending_cash_intent_does_not_block_uzum(
        self, client: AsyncClient, db: AsyncSession
    ):
        booking = await make_booking(db)
        db.add(
            Payment(
                booking_id=booking.id,
                method=PaymentMethod.CASH,
                status=PaymentStatus.PENDING,
                amount=Decimal("100.00"),
                currency="USD",
            )
        )
        await db.commit()

        resp = await client.post(
            f"{BASE}/create",
            json=create_body(booking.reservation_number, str(uuid.uuid4())),
            headers=auth_headers(),
        )
        assert resp.status_code == 200, resp.text

    async def test_duplicate_trans_id_is_rejected(
        self, client: AsyncClient, db: AsyncSession
    ):
        booking = await make_booking(db)
        trans_id = await open_transaction(client, booking)

        resp = await client.post(
            f"{BASE}/create",
            json=create_body(booking.reservation_number, trans_id),
            headers=auth_headers(),
        )
        assert resp.status_code == 400
        assert resp.json()["errorCode"] == "10010"

    async def test_second_transaction_for_same_booking_is_blocked(
        self, client: AsyncClient, db: AsyncSession
    ):
        booking = await make_booking(db)
        await open_transaction(client, booking)

        resp = await client.post(
            f"{BASE}/create",
            json=create_body(booking.reservation_number, str(uuid.uuid4())),
            headers=auth_headers(),
        )
        assert resp.status_code == 400
        assert resp.json()["errorCode"] == "10008"

    async def test_expired_transaction_frees_the_booking(
        self, client: AsyncClient, db: AsyncSession
    ):
        booking = await make_booking(db)
        stale = await open_transaction(client, booking)
        await _backdate(db, stale, minutes=45)

        second = str(uuid.uuid4())
        resp = await client.post(
            f"{BASE}/create",
            json=create_body(booking.reservation_number, second),
            headers=auth_headers(),
        )

        assert resp.status_code == 200, resp.text
        expired = await db.scalar(
            select(Payment).where(Payment.provider_payment_id == stale)
        )
        await db.refresh(expired)
        assert expired.status == PaymentStatus.FAILED

    async def test_missing_exchange_rate_is_internal_error(
        self, client: AsyncClient, db: AsyncSession
    ):
        user = await make_user(db, email="norate@test.com")
        sanatorium = await make_sanatorium(db)
        room = await make_room(db, sanatorium=sanatorium)
        booking = Booking(
            user_id=user.id,
            room_id=room.id,
            booking_type=BookingType.ROOM,
            check_in=date.today() + timedelta(days=5),
            check_out=date.today() + timedelta(days=6),
            guests=1,
            status=BookingStatus.PENDING,
            final_price=Decimal("100.00"),
            currency="EUR",
        )
        db.add(booking)
        await db.commit()
        await db.refresh(booking)

        resp = await client.post(
            f"{BASE}/create",
            json=create_body(booking.reservation_number, str(uuid.uuid4())),
            headers=auth_headers(),
        )
        assert resp.status_code == 400
        assert resp.json()["errorCode"] == "99999"


# --- /confirm ----------------------------------------------------------------


class TestConfirm:
    async def test_confirm_marks_payment_paid_and_booking_confirmed(
        self, client: AsyncClient, db: AsyncSession
    ):
        booking = await make_booking(db)
        trans_id = await open_transaction(client, booking)

        resp = await client.post(
            f"{BASE}/confirm", json=confirm_body(trans_id), headers=auth_headers()
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "CONFIRMED"
        assert body["amount"] == EXPECTED_TIYIN
        assert isinstance(body["confirmTime"], int)

        payment = await db.scalar(
            select(Payment).where(Payment.provider_payment_id == trans_id)
        )
        await db.refresh(payment)
        assert payment.status == PaymentStatus.PAID
        assert payment.paid_at is not None
        await db.refresh(booking)
        assert booking.status == BookingStatus.CONFIRMED

    async def test_unknown_trans_id_is_not_found(self, client: AsyncClient):
        resp = await client.post(
            f"{BASE}/confirm",
            json=confirm_body(str(uuid.uuid4())),
            headers=auth_headers(),
        )
        assert resp.status_code == 400
        assert resp.json()["errorCode"] == "10014"

    async def test_second_confirm_is_already_confirmed(
        self, client: AsyncClient, db: AsyncSession
    ):
        booking = await make_booking(db)
        trans_id = await open_transaction(client, booking)
        await client.post(
            f"{BASE}/confirm", json=confirm_body(trans_id), headers=auth_headers()
        )

        resp = await client.post(
            f"{BASE}/confirm", json=confirm_body(trans_id), headers=auth_headers()
        )
        assert resp.status_code == 400
        assert resp.json()["errorCode"] == "10016"

    async def test_expired_transaction_cannot_be_confirmed(
        self, client: AsyncClient, db: AsyncSession
    ):
        booking = await make_booking(db)
        trans_id = await open_transaction(client, booking)
        await _backdate(db, trans_id, minutes=45)

        resp = await client.post(
            f"{BASE}/confirm", json=confirm_body(trans_id), headers=auth_headers()
        )
        assert resp.status_code == 400
        assert resp.json()["errorCode"] == "10015"

    async def test_cancelled_booking_cannot_be_confirmed(
        self, client: AsyncClient, db: AsyncSession
    ):
        booking = await make_booking(db)
        trans_id = await open_transaction(client, booking)
        booking.status = BookingStatus.CANCELLED
        await db.commit()

        resp = await client.post(
            f"{BASE}/confirm", json=confirm_body(trans_id), headers=auth_headers()
        )
        assert resp.status_code == 400
        assert resp.json()["errorCode"] == "10015"


# --- /reverse ----------------------------------------------------------------


class TestReverse:
    async def test_reverse_before_confirm_cancels_payment(
        self, client: AsyncClient, db: AsyncSession
    ):
        booking = await make_booking(db)
        trans_id = await open_transaction(client, booking)

        resp = await client.post(
            f"{BASE}/reverse", json=trans_body(trans_id), headers=auth_headers()
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "REVERSED"
        payment = await db.scalar(
            select(Payment).where(Payment.provider_payment_id == trans_id)
        )
        await db.refresh(payment)
        assert payment.status == PaymentStatus.CANCELLED
        assert payment.cancelled_at is not None

    async def test_reverse_after_confirm_refunds_and_unconfirms_booking(
        self, client: AsyncClient, db: AsyncSession
    ):
        booking = await make_booking(db)
        trans_id = await open_transaction(client, booking)
        await client.post(
            f"{BASE}/confirm", json=confirm_body(trans_id), headers=auth_headers()
        )

        resp = await client.post(
            f"{BASE}/reverse", json=trans_body(trans_id), headers=auth_headers()
        )

        assert resp.status_code == 200, resp.text
        payment = await db.scalar(
            select(Payment).where(Payment.provider_payment_id == trans_id)
        )
        await db.refresh(payment)
        assert payment.status == PaymentStatus.REFUNDED
        await db.refresh(booking)
        assert booking.status == BookingStatus.PENDING

    async def test_second_reverse_is_already_reversed(
        self, client: AsyncClient, db: AsyncSession
    ):
        booking = await make_booking(db)
        trans_id = await open_transaction(client, booking)
        await client.post(
            f"{BASE}/reverse", json=trans_body(trans_id), headers=auth_headers()
        )

        resp = await client.post(
            f"{BASE}/reverse", json=trans_body(trans_id), headers=auth_headers()
        )
        assert resp.status_code == 400
        assert resp.json()["errorCode"] == "10018"

    async def test_unknown_trans_id_is_not_found(self, client: AsyncClient):
        resp = await client.post(
            f"{BASE}/reverse",
            json=trans_body(str(uuid.uuid4())),
            headers=auth_headers(),
        )
        assert resp.status_code == 400
        assert resp.json()["errorCode"] == "10014"


# --- /status -----------------------------------------------------------------


class TestStatus:
    async def test_created_then_confirmed_then_reversed(
        self, client: AsyncClient, db: AsyncSession
    ):
        booking = await make_booking(db)
        trans_id = await open_transaction(client, booking)

        created = await client.post(
            f"{BASE}/status", json=trans_body(trans_id), headers=auth_headers()
        )
        assert created.status_code == 200, created.text
        assert created.json()["status"] == "CREATED"
        assert created.json()["confirmTime"] is None
        assert created.json()["reverseTime"] is None

        await client.post(
            f"{BASE}/confirm", json=confirm_body(trans_id), headers=auth_headers()
        )
        confirmed = await client.post(
            f"{BASE}/status", json=trans_body(trans_id), headers=auth_headers()
        )
        assert confirmed.json()["status"] == "CONFIRMED"
        assert isinstance(confirmed.json()["confirmTime"], int)

        await client.post(
            f"{BASE}/reverse", json=trans_body(trans_id), headers=auth_headers()
        )
        reversed_ = await client.post(
            f"{BASE}/status", json=trans_body(trans_id), headers=auth_headers()
        )
        assert reversed_.json()["status"] == "REVERSED"
        assert isinstance(reversed_.json()["reverseTime"], int)

    async def test_expired_transaction_reports_failed(
        self, client: AsyncClient, db: AsyncSession
    ):
        booking = await make_booking(db)
        trans_id = await open_transaction(client, booking)
        await _backdate(db, trans_id, minutes=45)

        resp = await client.post(
            f"{BASE}/status", json=trans_body(trans_id), headers=auth_headers()
        )
        assert resp.status_code == 400
        assert resp.json()["status"] == "FAILED"
        assert resp.json()["errorCode"] == "10014"

    async def test_unknown_trans_id_is_not_found(self, client: AsyncClient):
        resp = await client.post(
            f"{BASE}/status",
            json=trans_body(str(uuid.uuid4())),
            headers=auth_headers(),
        )
        assert resp.status_code == 400
        assert resp.json()["errorCode"] == "10014"


# --- guest-facing order lookup ----------------------------------------------


class TestOrderInfo:
    async def test_owner_sees_order_id_and_uzs_amount(
        self, client: AsyncClient, db: AsyncSession, customer_user, customer_headers
    ):
        await make_exchange_rate(db)
        sanatorium = await make_sanatorium(db)
        room = await make_room(db, sanatorium=sanatorium)
        booking = Booking(
            user_id=customer_user.id,
            room_id=room.id,
            booking_type=BookingType.ROOM,
            check_in=date.today() + timedelta(days=3),
            check_out=date.today() + timedelta(days=5),
            guests=1,
            status=BookingStatus.PENDING,
            final_price=Decimal("100.00"),
            currency="USD",
        )
        db.add(booking)
        await db.commit()
        await db.refresh(booking)

        resp = await client.get(f"{BASE}/order/{booking.id}", headers=customer_headers)

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["order_id"] == booking.reservation_number
        assert body["service_id"] == SERVICE_ID
        assert Decimal(body["amount"]) == Decimal("1250000.00")
        assert body["currency"] == "UZS"

    async def test_other_customer_is_forbidden(
        self, client: AsyncClient, db: AsyncSession, customer_headers
    ):
        booking = await make_booking(db, email="someone-else@test.com")
        resp = await client.get(f"{BASE}/order/{booking.id}", headers=customer_headers)
        assert resp.status_code == 403

    async def test_anonymous_is_unauthorized(
        self, client: AsyncClient, db: AsyncSession
    ):
        booking = await make_booking(db)
        resp = await client.get(f"{BASE}/order/{booking.id}")
        assert resp.status_code == 401


async def _backdate(db: AsyncSession, trans_id: str, *, minutes: int) -> None:
    """Age a transaction past the confirmation window."""

    await db.execute(
        update(Payment)
        .where(Payment.provider_payment_id == trans_id)
        .values(created_at=datetime.now(UTC) - timedelta(minutes=minutes))
    )
    await db.commit()
