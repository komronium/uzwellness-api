"""Email-code-verified cancellation with admin approval (task 4)."""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sanatorium import SanatoriumStatus
from tests.factories import make_room, make_sanatorium

_CHECK_IN = "2027-05-10"
_CHECK_OUT = "2027-05-13"


async def _book(client: AsyncClient, db: AsyncSession, admin_user, customer_headers):
    san = await make_sanatorium(
        db, status=SanatoriumStatus.APPROVED, admin_user_id=admin_user.id
    )
    room = await make_room(
        db, sanatorium=san, capacity=2, min_nights=1, inventory_count=3
    )
    resp = await client.post(
        "/api/bookings",
        json={
            "room_id": str(room.id),
            "check_in": _CHECK_IN,
            "check_out": _CHECK_OUT,
            "guests": 2,
        },
        headers=customer_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _capture_codes(monkeypatch) -> dict:
    import app.services.cancellation_service as cs

    captured: dict = {}
    monkeypatch.setattr(cs, "send_cancellation_code", lambda **kw: captured.update(kw))
    return captured


async def test_full_request_confirm_approve(
    client, db, admin_user, customer_headers, admin_headers, monkeypatch
) -> None:
    codes = _capture_codes(monkeypatch)
    booking = await _book(client, db, admin_user, customer_headers)
    bid = booking["id"]

    requested = await client.post(
        f"/api/bookings/{bid}/cancellation/request", headers=customer_headers
    )
    assert requested.status_code == 202, requested.text
    assert requested.json()["status"] == "code_sent"
    code = codes["code"]
    assert len(code) == 6

    confirmed = await client.post(
        f"/api/bookings/{bid}/cancellation/confirm",
        json={"code": code},
        headers=customer_headers,
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "awaiting_approval"

    # Booking is still active until the admin approves.
    detail = await client.get(f"/api/bookings/{bid}", headers=customer_headers)
    assert detail.json()["status"] in {"pending", "confirmed"}

    approved = await client.post(
        f"/api/bookings/{bid}/cancellation/approve", headers=admin_headers
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "cancelled"


async def test_wrong_code_rejected(
    client, db, admin_user, customer_headers, monkeypatch
) -> None:
    _capture_codes(monkeypatch)
    booking = await _book(client, db, admin_user, customer_headers)
    bid = booking["id"]
    await client.post(
        f"/api/bookings/{bid}/cancellation/request", headers=customer_headers
    )
    resp = await client.post(
        f"/api/bookings/{bid}/cancellation/confirm",
        json={"code": "000000"},
        headers=customer_headers,
    )
    assert resp.status_code == 400


async def test_confirm_without_request_returns_404(
    client, db, admin_user, customer_headers
) -> None:
    booking = await _book(client, db, admin_user, customer_headers)
    resp = await client.post(
        f"/api/bookings/{booking['id']}/cancellation/confirm",
        json={"code": "123456"},
        headers=customer_headers,
    )
    assert resp.status_code == 404


async def test_admin_cannot_request_code_for_guest(
    client, db, admin_user, customer_headers, admin_headers, monkeypatch
) -> None:
    _capture_codes(monkeypatch)
    booking = await _book(client, db, admin_user, customer_headers)
    # The admin can see the booking but is not its owner.
    resp = await client.post(
        f"/api/bookings/{booking['id']}/cancellation/request", headers=admin_headers
    )
    assert resp.status_code == 403


async def test_reject_keeps_booking_active(
    client, db, admin_user, customer_headers, admin_headers, monkeypatch
) -> None:
    codes = _capture_codes(monkeypatch)
    booking = await _book(client, db, admin_user, customer_headers)
    bid = booking["id"]
    await client.post(
        f"/api/bookings/{bid}/cancellation/request", headers=customer_headers
    )
    await client.post(
        f"/api/bookings/{bid}/cancellation/confirm",
        json={"code": codes["code"]},
        headers=customer_headers,
    )
    rejected = await client.post(
        f"/api/bookings/{bid}/cancellation/reject", headers=admin_headers
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "rejected"

    detail = await client.get(f"/api/bookings/{bid}", headers=customer_headers)
    assert detail.json()["status"] != "cancelled"


async def test_approve_without_confirmation_returns_404(
    client, db, admin_user, customer_headers, admin_headers, monkeypatch
) -> None:
    _capture_codes(monkeypatch)
    booking = await _book(client, db, admin_user, customer_headers)
    bid = booking["id"]
    # Code requested but never confirmed -> nothing awaiting approval.
    await client.post(
        f"/api/bookings/{bid}/cancellation/request", headers=customer_headers
    )
    resp = await client.post(
        f"/api/bookings/{bid}/cancellation/approve", headers=admin_headers
    )
    assert resp.status_code == 404
