"""Integration + concurrency tests for the booking flow (v0.4)."""
import asyncio
from datetime import date, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sanatorium import SanatoriumStatus
from app.models.user import UserRole
from tests.factories import make_room, make_sanatorium, make_user

# ── helpers ────────────────────────────────────────────────────────────────

_CHECK_IN = "2027-03-10"
_CHECK_OUT = "2027-03-14"  # 4 nights
_DATES_START = date(2027, 3, 10)
_DATES_END = date(2027, 3, 14)


async def _setup_room_with_availability(
    db, client, admin_user, admin_headers, *, units: int = 5, capacity: int = 2
):
    san = await make_sanatorium(
        db, status=SanatoriumStatus.APPROVED, admin_user_id=admin_user.id
    )
    room = await make_room(
        db,
        sanatorium=san,
        capacity=capacity,
        min_nights=1,
        inventory_count=units,
    )
    return san, room


# ── e2e: register → search → book → cancel → re-book ──────────────────────

class TestEndToEnd:
    async def test_full_lifecycle(
        self,
        client: AsyncClient,
        db: AsyncSession,
        admin_user,
        admin_headers,
    ):
        san, room = await _setup_room_with_availability(
            db, client, admin_user, admin_headers, units=3
        )

        # 1. Register new customer
        reg = await client.post(
            "/api/auth/register",
            json={
                "email": "traveller@test.com",
                "password": "Travel123!",
                "full_name": "Test Traveller",
            },
        )
        assert reg.status_code == 201
        login = await client.post(
            "/api/auth/login",
            json={"email": "traveller@test.com", "password": "Travel123!"},
        )
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        # 2. Search — should find the room
        search = await client.get(
            f"/api/rooms/search?check_in={_CHECK_IN}&check_out={_CHECK_OUT}&guests=2"
        )
        assert search.status_code == 200
        assert any(r["id"] == str(room.id) for r in search.json())

        # 3. Book
        booking_resp = await client.post(
            "/api/bookings",
            json={
                "room_id": str(room.id),
                "check_in": _CHECK_IN,
                "check_out": _CHECK_OUT,
                "guests": 2,
            },
            headers=headers,
        )
        assert booking_resp.status_code == 201
        booking = booking_resp.json()
        assert booking["status"] == "confirmed"
        assert booking["guests"] == 2
        assert len(booking["code"]) == 8

        # 4. Customer sees it in their list
        lst = await client.get("/api/bookings", headers=headers)
        assert any(b["id"] == booking["id"] for b in lst.json()["items"])

        # 5. Cancel
        cancel = await client.patch(
            f"/api/bookings/{booking['id']}/cancel", headers=headers
        )
        assert cancel.status_code == 200
        assert cancel.json()["status"] == "cancelled"

        # 6. Availability restored → can book again
        rebook = await client.post(
            "/api/bookings",
            json={
                "room_id": str(room.id),
                "check_in": _CHECK_IN,
                "check_out": _CHECK_OUT,
                "guests": 2,
            },
            headers=headers,
        )
        assert rebook.status_code == 201
        assert rebook.json()["status"] == "confirmed"


# ── booking validation ─────────────────────────────────────────────────────

class TestBookingValidation:
    async def test_check_in_in_past_returns_400(
        self, client, db, admin_user, admin_headers, customer_headers
    ):
        san, room = await _setup_room_with_availability(
            db, client, admin_user, admin_headers
        )
        resp = await client.post(
            "/api/bookings",
            json={
                "room_id": str(room.id),
                "check_in": "2020-01-01",
                "check_out": "2020-01-05",
                "guests": 1,
            },
            headers=customer_headers,
        )
        assert resp.status_code == 400

    async def test_min_nights_enforced(
        self, client, db, admin_user, admin_headers, customer_headers
    ):
        san = await make_sanatorium(
            db, status=SanatoriumStatus.APPROVED, admin_user_id=admin_user.id
        )
        room = await make_room(
            db, sanatorium=san, min_nights=3, inventory_count=5
        )
        # Only 1 night — below min_nights=3
        resp = await client.post(
            "/api/bookings",
            json={
                "room_id": str(room.id),
                "check_in": _CHECK_IN,
                "check_out": str(_DATES_START + timedelta(days=1)),
                "guests": 1,
            },
            headers=customer_headers,
        )
        assert resp.status_code == 400

    async def test_multi_unit_booking_books_enough_rooms(
        self, client, db, admin_user, admin_headers, customer_headers
    ):
        # 5 rooms, capacity 2 each. Booking for 5 guests → 3 rooms reserved.
        san, room = await _setup_room_with_availability(
            db, client, admin_user, admin_headers, units=5, capacity=2
        )
        resp = await client.post(
            "/api/bookings",
            json={
                "room_id": str(room.id),
                "check_in": _CHECK_IN,
                "check_out": _CHECK_OUT,
                "guests": 5,
            },
            headers=customer_headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["guests"] == 5
        assert body["rooms_count"] == 3  # ceil(5/2)

    async def test_multi_unit_booking_exceeds_inventory_returns_409(
        self, client, db, admin_user, admin_headers, customer_headers
    ):
        # Only 2 rooms exist but 5 guests → need 3 → 409
        san, room = await _setup_room_with_availability(
            db, client, admin_user, admin_headers, units=2, capacity=2
        )
        resp = await client.post(
            "/api/bookings",
            json={
                "room_id": str(room.id),
                "check_in": _CHECK_IN,
                "check_out": _CHECK_OUT,
                "guests": 5,
            },
            headers=customer_headers,
        )
        assert resp.status_code == 409

    async def test_no_inventory_returns_409(
        self, client, db, admin_user, customer_headers
    ):
        san = await make_sanatorium(
            db, status=SanatoriumStatus.APPROVED, admin_user_id=admin_user.id
        )
        room = await make_room(db, sanatorium=san, inventory_count=1)
        # Drop inventory to 0 → no units to sell
        room.inventory_count = 0
        await db.commit()
        resp = await client.post(
            "/api/bookings",
            json={
                "room_id": str(room.id),
                "check_in": _CHECK_IN,
                "check_out": _CHECK_OUT,
                "guests": 1,
            },
            headers=customer_headers,
        )
        assert resp.status_code == 409

    async def test_unauthenticated_returns_401(self, client, db, admin_user, admin_headers):
        san, room = await _setup_room_with_availability(
            db, client, admin_user, admin_headers
        )
        resp = await client.post(
            "/api/bookings",
            json={
                "room_id": str(room.id),
                "check_in": _CHECK_IN,
                "check_out": _CHECK_OUT,
                "guests": 1,
            },
        )
        assert resp.status_code == 401


# ── RBAC for listing ───────────────────────────────────────────────────────

class TestBookingRBAC:
    async def test_customer_sees_only_own(
        self, client, db, admin_user, admin_headers, customer_user, customer_headers
    ):
        san, room = await _setup_room_with_availability(
            db, client, admin_user, admin_headers, units=10
        )
        other = await make_user(db, email="other2@test.com", role=UserRole.CUSTOMER)
        login = await client.post(
            "/api/auth/login",
            json={"email": other.email, "password": "passw0rd"},
        )
        other_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        payload = {
            "room_id": str(room.id),
            "check_in": _CHECK_IN,
            "check_out": _CHECK_OUT,
            "guests": 1,
        }
        await client.post("/api/bookings", json=payload, headers=customer_headers)
        await client.post("/api/bookings", json=payload, headers=other_headers)

        resp = await client.get("/api/bookings", headers=customer_headers)
        assert resp.json()["total"] == 1

    async def test_admin_sees_own_sanatorium_bookings(
        self, client, db, admin_user, admin_headers, customer_headers
    ):
        san, room = await _setup_room_with_availability(
            db, client, admin_user, admin_headers, units=10
        )
        other_admin = await make_user(db, email="admin2@test.com", role=UserRole.ADMIN)
        other_san = await make_sanatorium(db, name="Other Sanatorium", admin_user_id=other_admin.id)
        await make_room(db, sanatorium=other_san)

        await client.post(
            "/api/bookings",
            json={
                "room_id": str(room.id),
                "check_in": _CHECK_IN,
                "check_out": _CHECK_OUT,
                "guests": 1,
            },
            headers=customer_headers,
        )
        resp = await client.get("/api/bookings", headers=admin_headers)
        assert resp.json()["total"] == 1
        assert resp.json()["items"][0]["room_id"] == str(room.id)

    async def test_super_admin_sees_all(
        self, client, db, admin_user, admin_headers, customer_headers, super_admin_headers
    ):
        san, room = await _setup_room_with_availability(
            db, client, admin_user, admin_headers, units=10
        )
        payload = {
            "room_id": str(room.id),
            "check_in": _CHECK_IN,
            "check_out": _CHECK_OUT,
            "guests": 1,
        }
        await client.post("/api/bookings", json=payload, headers=customer_headers)
        await client.post("/api/bookings", json=payload, headers=customer_headers)

        resp = await client.get("/api/bookings", headers=super_admin_headers)
        assert resp.json()["total"] >= 2


# ── cancellation ───────────────────────────────────────────────────────────

class TestCancellation:
    async def test_customer_cancels_own(
        self, client, db, admin_user, admin_headers, customer_headers
    ):
        san, room = await _setup_room_with_availability(
            db, client, admin_user, admin_headers
        )
        b = (
            await client.post(
                "/api/bookings",
                json={
                    "room_id": str(room.id),
                    "check_in": _CHECK_IN,
                    "check_out": _CHECK_OUT,
                    "guests": 1,
                },
                headers=customer_headers,
            )
        ).json()
        cancel = await client.patch(
            f"/api/bookings/{b['id']}/cancel", headers=customer_headers
        )
        assert cancel.status_code == 200
        assert cancel.json()["status"] == "cancelled"

    async def test_cannot_cancel_twice(
        self, client, db, admin_user, admin_headers, customer_headers
    ):
        san, room = await _setup_room_with_availability(
            db, client, admin_user, admin_headers
        )
        b = (
            await client.post(
                "/api/bookings",
                json={
                    "room_id": str(room.id),
                    "check_in": _CHECK_IN,
                    "check_out": _CHECK_OUT,
                    "guests": 1,
                },
                headers=customer_headers,
            )
        ).json()
        await client.patch(f"/api/bookings/{b['id']}/cancel", headers=customer_headers)
        second = await client.patch(
            f"/api/bookings/{b['id']}/cancel", headers=customer_headers
        )
        assert second.status_code == 409

    async def test_customer_cannot_cancel_others(
        self, client, db, admin_user, admin_headers, customer_headers
    ):
        san, room = await _setup_room_with_availability(
            db, client, admin_user, admin_headers, units=10
        )
        other = await make_user(db, email="other3@test.com", role=UserRole.CUSTOMER)
        login = await client.post(
            "/api/auth/login", json={"email": other.email, "password": "passw0rd"}
        )
        other_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        b = (
            await client.post(
                "/api/bookings",
                json={
                    "room_id": str(room.id),
                    "check_in": _CHECK_IN,
                    "check_out": _CHECK_OUT,
                    "guests": 1,
                },
                headers=customer_headers,
            )
        ).json()
        resp = await client.patch(
            f"/api/bookings/{b['id']}/cancel", headers=other_headers
        )
        assert resp.status_code == 404  # not visible to other customer

    async def test_super_admin_cancels_any(
        self, client, db, admin_user, admin_headers, customer_headers, super_admin_headers
    ):
        san, room = await _setup_room_with_availability(
            db, client, admin_user, admin_headers
        )
        b = (
            await client.post(
                "/api/bookings",
                json={
                    "room_id": str(room.id),
                    "check_in": _CHECK_IN,
                    "check_out": _CHECK_OUT,
                    "guests": 1,
                },
                headers=customer_headers,
            )
        ).json()
        cancel = await client.patch(
            f"/api/bookings/{b['id']}/cancel", headers=super_admin_headers
        )
        assert cancel.status_code == 200
        assert cancel.json()["status"] == "cancelled"

    async def test_cancel_restores_multi_unit_availability(
        self, client, db, admin_user, admin_headers, customer_headers
    ):
        # 5 guests → 3 rooms booked, cancel should restore all 3
        san, room = await _setup_room_with_availability(
            db, client, admin_user, admin_headers, units=5, capacity=2
        )
        b = (
            await client.post(
                "/api/bookings",
                json={
                    "room_id": str(room.id),
                    "check_in": _CHECK_IN,
                    "check_out": _CHECK_OUT,
                    "guests": 5,
                },
                headers=customer_headers,
            )
        ).json()
        assert b["rooms_count"] == 3
        avail = await client.get(
            f"/api/rooms/{room.id}/availability?from={_CHECK_IN}&to={_CHECK_OUT}"
        )
        assert all(r["units_booked"] == 3 for r in avail.json())

        await client.patch(f"/api/bookings/{b['id']}/cancel", headers=customer_headers)
        avail2 = await client.get(
            f"/api/rooms/{room.id}/availability?from={_CHECK_IN}&to={_CHECK_OUT}"
        )
        assert all(r["units_booked"] == 0 for r in avail2.json())

    async def test_cancel_restores_availability(
        self, client, db, admin_user, admin_headers, customer_headers
    ):
        san, room = await _setup_room_with_availability(
            db, client, admin_user, admin_headers, units=1
        )
        b = (
            await client.post(
                "/api/bookings",
                json={
                    "room_id": str(room.id),
                    "check_in": _CHECK_IN,
                    "check_out": _CHECK_OUT,
                    "guests": 1,
                },
                headers=customer_headers,
            )
        ).json()
        # After booking, units_booked should be 1 (sold out)
        avail = await client.get(
            f"/api/rooms/{room.id}/availability?from={_CHECK_IN}&to={_CHECK_OUT}"
        )
        assert all(r["units_booked"] == 1 for r in avail.json())
        assert all(r["units_available"] == 0 for r in avail.json())

        await client.patch(f"/api/bookings/{b['id']}/cancel", headers=customer_headers)

        # After cancel, units_booked back to 0 → available again
        avail2 = await client.get(
            f"/api/rooms/{room.id}/availability?from={_CHECK_IN}&to={_CHECK_OUT}"
        )
        assert all(r["units_booked"] == 0 for r in avail2.json())
        assert all(r["units_available"] == 1 for r in avail2.json())

    async def test_cancel_flips_paid_payments_to_refund_pending(
        self, client, db, admin_user, admin_headers, customer_headers
    ):
        from decimal import Decimal
        from uuid import UUID

        from sqlalchemy import select as _select

        from app.models.payment import Payment, PaymentMethod, PaymentStatus

        san, room = await _setup_room_with_availability(
            db, client, admin_user, admin_headers
        )
        b = (
            await client.post(
                "/api/bookings",
                json={
                    "room_id": str(room.id),
                    "check_in": _CHECK_IN,
                    "check_out": _CHECK_OUT,
                    "guests": 1,
                },
                headers=customer_headers,
            )
        ).json()
        booking_id = UUID(b["id"])

        # Simulate a successful card payment + a stale pending payment.
        db.add(
            Payment(
                booking_id=booking_id,
                method=PaymentMethod.PAYME,
                status=PaymentStatus.PAID,
                amount=Decimal("100.00"),
                currency="USD",
            )
        )
        db.add(
            Payment(
                booking_id=booking_id,
                method=PaymentMethod.CLICK,
                status=PaymentStatus.PENDING,
                amount=Decimal("100.00"),
                currency="USD",
            )
        )
        await db.commit()

        cancel = await client.patch(
            f"/api/bookings/{booking_id}/cancel", headers=customer_headers
        )
        assert cancel.status_code == 200

        rows = list(
            (
                await db.execute(
                    _select(Payment).where(Payment.booking_id == booking_id)
                )
            ).scalars()
        )
        statuses = {r.method: r.status for r in rows}
        assert statuses[PaymentMethod.PAYME] == PaymentStatus.REFUND_PENDING
        assert statuses[PaymentMethod.CLICK] == PaymentStatus.CANCELLED


# ── concurrency: two requests racing for the last unit ────────────────────

class TestConcurrency:
    async def test_last_unit_only_one_booking_succeeds(
        self, client, db, admin_user, admin_headers, customer_user, customer_headers
    ):
        san, room = await _setup_room_with_availability(
            db, client, admin_user, admin_headers, units=1, capacity=4
        )
        payload = {
            "room_id": str(room.id),
            "check_in": _CHECK_IN,
            "check_out": _CHECK_OUT,
            "guests": 1,
        }

        r1, r2 = await asyncio.gather(
            client.post("/api/bookings", json=payload, headers=customer_headers),
            client.post("/api/bookings", json=payload, headers=customer_headers),
        )

        codes = sorted([r1.status_code, r2.status_code])
        assert codes == [201, 409], (
            f"Expected exactly one success and one conflict, got {codes}"
        )
