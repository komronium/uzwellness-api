import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking, BookingStatus, BookingType
from app.models.user import UserRole
from tests.factories import make_user


_FLIGHT_TIME = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
_RETURN_TIME = (datetime.now(timezone.utc) + timedelta(days=12)).isoformat()


def _arrival_payload(**overrides) -> dict:
    base = {
        "direction": "arrival",
        "pickup_location": "Tashkent International Airport",
        "dropoff_location": "Charvak Sanatorium",
        "flight_number": "HY101",
        "flight_time": _FLIGHT_TIME,
        "passengers_count": 2,
        "vehicle_type": "sedan",
        "contact_phone": "+998 90 123 45 67",
    }
    base.update(overrides)
    return base


# ── create ─────────────────────────────────────────────────────────────────


async def test_customer_creates_arrival_transfer(
    client: AsyncClient, customer_user, customer_headers
) -> None:
    resp = await client.post(
        "/api/transfers", json=_arrival_payload(), headers=customer_headers
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "requested"
    assert body["direction"] == "arrival"
    assert body["user_id"] == str(customer_user.id)
    assert body["price"] is None  # super_admin sets later


async def test_round_trip_requires_return_flight_time(
    client: AsyncClient, customer_headers
) -> None:
    bad = _arrival_payload(direction="round_trip")
    resp = await client.post("/api/transfers", json=bad, headers=customer_headers)
    assert resp.status_code == 422


async def test_departure_does_not_require_flight_time(
    client: AsyncClient, customer_headers
) -> None:
    payload = {
        "direction": "departure",
        "pickup_location": "Charvak Sanatorium",
        "dropoff_location": "Tashkent Airport",
        "passengers_count": 1,
    }
    resp = await client.post(
        "/api/transfers", json=payload, headers=customer_headers
    )
    assert resp.status_code == 201, resp.text


async def test_return_flight_only_for_round_trip(
    client: AsyncClient, customer_headers
) -> None:
    bad = _arrival_payload(return_flight_time=_RETURN_TIME)
    resp = await client.post("/api/transfers", json=bad, headers=customer_headers)
    assert resp.status_code == 422


async def test_round_trip_return_must_be_after_outbound(
    client: AsyncClient, customer_headers
) -> None:
    payload = _arrival_payload(
        direction="round_trip",
        return_flight_time=(
            datetime.now(timezone.utc) - timedelta(days=1)
        ).isoformat(),
    )
    resp = await client.post(
        "/api/transfers", json=payload, headers=customer_headers
    )
    assert resp.status_code == 422


async def test_anonymous_cannot_create(client: AsyncClient) -> None:
    resp = await client.post("/api/transfers", json=_arrival_payload())
    assert resp.status_code == 401


# ── list / get visibility ──────────────────────────────────────────────────


async def test_customer_sees_only_own_transfers(
    client: AsyncClient,
    db: AsyncSession,
    customer_user,
    customer_headers,
) -> None:
    other = await make_user(
        db, email="other-tr@test.com", role=UserRole.CUSTOMER
    )
    other_login = await client.post(
        "/api/auth/login",
        json={"email": other.email, "password": "passw0rd"},
    )
    other_headers = {
        "Authorization": f"Bearer {other_login.json()['access_token']}"
    }
    await client.post("/api/transfers", json=_arrival_payload(), headers=customer_headers)
    await client.post("/api/transfers", json=_arrival_payload(), headers=other_headers)

    me = await client.get("/api/transfers", headers=customer_headers)
    assert me.json()["total"] == 1
    assert me.json()["items"][0]["user_id"] == str(customer_user.id)


async def test_super_admin_sees_all_transfers(
    client: AsyncClient, customer_headers, super_admin_headers
) -> None:
    await client.post("/api/transfers", json=_arrival_payload(), headers=customer_headers)
    await client.post("/api/transfers", json=_arrival_payload(), headers=customer_headers)
    resp = await client.get("/api/transfers", headers=super_admin_headers)
    assert resp.json()["total"] == 2


async def test_customer_cannot_view_others_transfer(
    client: AsyncClient,
    db: AsyncSession,
    customer_headers,
) -> None:
    created = await client.post(
        "/api/transfers", json=_arrival_payload(), headers=customer_headers
    )
    tid = created.json()["id"]
    other = await make_user(
        db, email="snoop-tr@test.com", role=UserRole.CUSTOMER
    )
    other_login = await client.post(
        "/api/auth/login",
        json={"email": other.email, "password": "passw0rd"},
    )
    other_headers = {
        "Authorization": f"Bearer {other_login.json()['access_token']}"
    }
    resp = await client.get(f"/api/transfers/{tid}", headers=other_headers)
    assert resp.status_code == 404


async def test_list_filters_by_status(
    client: AsyncClient, customer_headers, super_admin_headers
) -> None:
    created = await client.post(
        "/api/transfers", json=_arrival_payload(), headers=customer_headers
    )
    await client.post(
        "/api/transfers", json=_arrival_payload(), headers=customer_headers
    )
    # confirm one
    tid = created.json()["id"]
    await client.patch(
        f"/api/transfers/{tid}",
        json={"status": "confirmed"},
        headers=super_admin_headers,
    )
    resp = await client.get(
        "/api/transfers?status=requested", headers=super_admin_headers
    )
    assert resp.json()["total"] == 1
    assert resp.json()["items"][0]["status"] == "requested"


# ── super_admin update ──────────────────────────────────────────────────────


async def test_super_admin_dispatches_transfer(
    client: AsyncClient, customer_headers, super_admin_headers
) -> None:
    created = await client.post(
        "/api/transfers", json=_arrival_payload(), headers=customer_headers
    )
    tid = created.json()["id"]
    resp = await client.patch(
        f"/api/transfers/{tid}",
        json={
            "status": "confirmed",
            "price": "30.00",
            "currency": "USD",
            "driver_name": "Akmal Karimov",
            "driver_phone": "+998 90 987 65 43",
        },
        headers=super_admin_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "confirmed"
    assert body["price"] == "30.00"
    assert body["driver_name"] == "Akmal Karimov"


async def test_price_without_currency_rejected(
    client: AsyncClient, customer_headers, super_admin_headers
) -> None:
    created = await client.post(
        "/api/transfers", json=_arrival_payload(), headers=customer_headers
    )
    tid = created.json()["id"]
    resp = await client.patch(
        f"/api/transfers/{tid}",
        json={"price": "30.00"},
        headers=super_admin_headers,
    )
    assert resp.status_code == 400


async def test_customer_cannot_update_transfer(
    client: AsyncClient, customer_headers
) -> None:
    created = await client.post(
        "/api/transfers", json=_arrival_payload(), headers=customer_headers
    )
    tid = created.json()["id"]
    resp = await client.patch(
        f"/api/transfers/{tid}",
        json={"status": "confirmed"},
        headers=customer_headers,
    )
    assert resp.status_code == 403


# ── cancel ─────────────────────────────────────────────────────────────────


async def test_customer_cancels_own_transfer(
    client: AsyncClient, customer_headers
) -> None:
    created = await client.post(
        "/api/transfers", json=_arrival_payload(), headers=customer_headers
    )
    tid = created.json()["id"]
    resp = await client.patch(
        f"/api/transfers/{tid}/cancel", headers=customer_headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "cancelled"


async def test_cannot_cancel_completed_transfer(
    client: AsyncClient, customer_headers, super_admin_headers
) -> None:
    created = await client.post(
        "/api/transfers", json=_arrival_payload(), headers=customer_headers
    )
    tid = created.json()["id"]
    await client.patch(
        f"/api/transfers/{tid}",
        json={"status": "completed"},
        headers=super_admin_headers,
    )
    resp = await client.patch(
        f"/api/transfers/{tid}/cancel", headers=customer_headers
    )
    assert resp.status_code == 409


# ── 404 ────────────────────────────────────────────────────────────────────


async def test_update_unknown_transfer_returns_404(
    client: AsyncClient, super_admin_headers
) -> None:
    resp = await client.patch(
        f"/api/transfers/{uuid.uuid4()}",
        json={"status": "confirmed"},
        headers=super_admin_headers,
    )
    assert resp.status_code == 404


# ── super_admin attaches to customer's booking → user_id = customer ───────


async def test_super_admin_attach_to_customer_booking_assigns_customer(
    client: AsyncClient,
    db: AsyncSession,
    customer_user,
    super_admin_headers,
) -> None:
    # ck_bookings_type_links_consistent allows status='cancelled' with all
    # link FKs NULL — that's enough to test the user_id propagation logic.
    booking = Booking(
        user_id=customer_user.id,
        booking_type=BookingType.ROOM,
        check_in=date.today() + timedelta(days=10),
        check_out=date.today() + timedelta(days=12),
        guests=1,
        rooms_count=1,
        status=BookingStatus.CANCELLED,
        final_price=Decimal("100.00"),
        currency="USD",
    )
    db.add(booking)
    await db.commit()

    payload = _arrival_payload(booking_id=str(booking.id))
    resp = await client.post(
        "/api/transfers", json=payload, headers=super_admin_headers
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    # user_id should point to the booking's customer, not the super_admin.
    assert body["user_id"] == str(customer_user.id)
