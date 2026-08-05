"""Uzum Checkout merchant callbacks — receive, record, acknowledge.

The contract Uzum relies on is narrow but strict: answer 200 with an empty
JSON object, or the callback is redelivered up to five times.
"""

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.uzum_checkout_event import UzumCheckoutCallbackKind, UzumCheckoutEvent

BASE = "/api/payments/uzum-checkout"

ORDER_ID = "b3e1eced-f2bd-4d8c-9765-fbc9d1d222d5"
ORDER_NUMBER = "2608040105340758"


def acquiring_body(**overrides) -> dict:
    body = {
        "orderId": ORDER_ID,
        "orderNumber": ORDER_NUMBER,
        "operationState": "SUCCESS",
        "operationType": "COMPLETE",
        "cardType": 2,
        "rrn": "123456789012",
    }
    return {**body, **overrides}


async def _only_event(db: AsyncSession) -> UzumCheckoutEvent:
    rows = (await db.scalars(select(UzumCheckoutEvent))).all()
    assert len(rows) == 1, rows
    return rows[0]


class TestAcknowledgement:
    async def test_acquiring_callback_is_acknowledged(
        self, client: AsyncClient, db: AsyncSession
    ):
        resp = await client.post(f"{BASE}/callback", json=acquiring_body())
        assert resp.status_code == 200, resp.text
        # Uzum treats anything other than 200 + {} as a delivery failure.
        assert resp.json() == {}

        event = await _only_event(db)
        assert event.kind == UzumCheckoutCallbackKind.ACQUIRING
        assert event.order_id == ORDER_ID
        assert event.order_number == ORDER_NUMBER
        assert event.operation_state == "SUCCESS"
        assert event.operation_type == "COMPLETE"
        assert event.rrn == "123456789012"
        assert event.payload == acquiring_body()

    async def test_event_callback_is_acknowledged(
        self, client: AsyncClient, db: AsyncSession
    ):
        resp = await client.post(
            f"{BASE}/event",
            json={
                "orderId": ORDER_ID,
                "orderNumber": ORDER_NUMBER,
                "eventType": "FORM_CLOSED",
                "actionCode": 3042,
                "actionCodeDescription": "User closed the payment form",
            },
        )
        assert resp.status_code == 200, resp.text
        assert resp.json() == {}

        event = await _only_event(db)
        assert event.kind == UzumCheckoutCallbackKind.EVENT
        assert event.event_type == "FORM_CLOSED"

    async def test_receipt_callback_is_acknowledged(
        self, client: AsyncClient, db: AsyncSession
    ):
        resp = await client.post(
            f"{BASE}/receipt",
            json={
                "orderId": ORDER_ID,
                "receiptType": "PURCHASE",
                "receiptUrl": "https://receipts.uzum.uz/abc123",
            },
        )
        assert resp.status_code == 200, resp.text
        assert resp.json() == {}

        event = await _only_event(db)
        assert event.kind == UzumCheckoutCallbackKind.RECEIPT
        assert event.receipt_type == "PURCHASE"
        assert event.receipt_url == "https://receipts.uzum.uz/abc123"


class TestResilience:
    async def test_unknown_fields_are_kept(self, client: AsyncClient, db: AsyncSession):
        """A field Uzum adds later must not cost us the notification."""
        body = acquiring_body(somethingNew="future", nested={"a": 1})
        resp = await client.post(f"{BASE}/callback", json=body)
        assert resp.status_code == 200

        event = await _only_event(db)
        assert event.payload["somethingNew"] == "future"
        assert event.operation_state == "SUCCESS"

    async def test_missing_fields_are_tolerated(
        self, client: AsyncClient, db: AsyncSession
    ):
        resp = await client.post(f"{BASE}/callback", json={"orderId": ORDER_ID})
        assert resp.status_code == 200
        assert resp.json() == {}

        event = await _only_event(db)
        assert event.order_id == ORDER_ID
        assert event.operation_state is None

    async def test_malformed_body_is_still_acknowledged(
        self, client: AsyncClient, db: AsyncSession
    ):
        """Redelivering an unparseable body cannot help, so don't ask for it."""
        resp = await client.post(
            f"{BASE}/callback",
            content=b"not json at all",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 200
        assert resp.json() == {}

        event = await _only_event(db)
        assert event.payload["_unparsed"] == "not json at all"

    async def test_retries_are_all_recorded(
        self, client: AsyncClient, db: AsyncSession
    ):
        """Uzum redelivers up to 5 times; the log keeps every delivery."""
        for _ in range(3):
            resp = await client.post(f"{BASE}/callback", json=acquiring_body())
            assert resp.status_code == 200

        rows = (await db.scalars(select(UzumCheckoutEvent))).all()
        assert len(rows) == 3

    async def test_source_ip_is_recorded_from_forwarded_header(
        self, client: AsyncClient, db: AsyncSession
    ):
        """Onboarding needs the real source IPs for the nginx allowlist."""
        resp = await client.post(
            f"{BASE}/callback",
            json=acquiring_body(),
            headers={"X-Forwarded-For": "91.204.239.10, 10.0.0.1"},
        )
        assert resp.status_code == 200

        event = await _only_event(db)
        assert event.source_ip == "91.204.239.10"


class TestNoSideEffects:
    async def test_callback_is_not_applied_yet(
        self, client: AsyncClient, db: AsyncSession
    ):
        """Unsigned callbacks must not move money before getOrderStatus."""
        await client.post(f"{BASE}/callback", json=acquiring_body())
        event = await _only_event(db)
        assert event.processed_at is None

    async def test_callbacks_need_no_authentication(self, client: AsyncClient):
        """Uzum sends no credentials — requiring any would break delivery."""
        resp = await client.post(f"{BASE}/callback", json=acquiring_body())
        assert resp.status_code == 200

    async def test_get_is_not_allowed(self, client: AsyncClient):
        assert (await client.get(f"{BASE}/callback")).status_code == 405
