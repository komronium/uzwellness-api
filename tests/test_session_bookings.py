"""Integration tests for SESSION bookings (treatment_programs as bookable units)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.program import TreatmentProgram
from app.models.sanatorium import SanatoriumStatus
from app.models.user import UserRole
from tests.factories import make_sanatorium, make_user


_FUTURE = (date.today() + timedelta(days=30)).isoformat()


async def _make_session_program(
    db: AsyncSession,
    *,
    sanatorium_id,
    price: str = "50.00",
    currency: str = "USD",
    group_size_max: int | None = None,
) -> TreatmentProgram:
    program = TreatmentProgram(
        sanatorium_id=sanatorium_id,
        name={"en": "Yoga session"},
        description={},
        price=Decimal(price),
        currency=currency,
        group_size_max=group_size_max,
        instructor_bio={},
        what_to_bring={},
    )
    db.add(program)
    await db.commit()
    await db.refresh(program)
    return program


async def _customer_headers(client: AsyncClient, db: AsyncSession) -> dict:
    await make_user(
        db,
        email="customer-sess@test.com",
        password="customerpass123",
        role=UserRole.CUSTOMER,
    )
    login = await client.post(
        "/api/auth/login",
        json={"email": "customer-sess@test.com", "password": "customerpass123"},
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


class TestSessionBookingHappyPath:
    async def test_book_session_for_one_guest(
        self, client: AsyncClient, db: AsyncSession
    ):
        san = await make_sanatorium(
            db, slug="yoga-san", status=SanatoriumStatus.APPROVED
        )
        program = await _make_session_program(db, sanatorium_id=san.id, price="80.00")
        headers = await _customer_headers(client, db)
        resp = await client.post(
            "/api/bookings",
            json={
                "program_id": str(program.id),
                "check_in": _FUTURE,
                "guests": 1,
            },
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["booking_type"] == "session"
        assert body["program_id"] == str(program.id)
        assert body["final_price"] == "80.00"
        assert body["currency"] == "USD"

    async def test_price_multiplies_by_guests(
        self, client: AsyncClient, db: AsyncSession
    ):
        san = await make_sanatorium(db, slug="yoga-2")
        program = await _make_session_program(db, sanatorium_id=san.id, price="50.00")
        headers = await _customer_headers(client, db)
        resp = await client.post(
            "/api/bookings",
            json={
                "program_id": str(program.id),
                "check_in": _FUTURE,
                "guests": 3,
            },
            headers=headers,
        )
        assert resp.status_code == 201
        assert resp.json()["final_price"] == "150.00"

    async def test_check_out_defaults_to_check_in(
        self, client: AsyncClient, db: AsyncSession
    ):
        san = await make_sanatorium(db, slug="yoga-3")
        program = await _make_session_program(db, sanatorium_id=san.id)
        headers = await _customer_headers(client, db)
        resp = await client.post(
            "/api/bookings",
            json={
                "program_id": str(program.id),
                "check_in": _FUTURE,
                "guests": 1,
            },
            headers=headers,
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["check_in"] == _FUTURE
        assert body["check_out"] == _FUTURE


class TestSessionBookingValidation:
    async def test_program_without_price_returns_400(
        self, client: AsyncClient, db: AsyncSession
    ):
        san = await make_sanatorium(db, slug="bundle-only")
        # Bundled program (no price/currency) — not directly bookable
        program = TreatmentProgram(
            sanatorium_id=san.id,
            name={"en": "Bundled treatment"},
            description={},
            min_nights=5,
            max_nights=10,
            instructor_bio={},
            what_to_bring={},
        )
        db.add(program)
        await db.commit()
        await db.refresh(program)

        headers = await _customer_headers(client, db)
        resp = await client.post(
            "/api/bookings",
            json={"program_id": str(program.id), "check_in": _FUTURE, "guests": 1},
            headers=headers,
        )
        assert resp.status_code == 400
        assert "not bookable" in resp.json()["detail"].lower()

    async def test_inactive_program_returns_404(
        self, client: AsyncClient, db: AsyncSession
    ):
        san = await make_sanatorium(db, slug="yoga-off")
        program = await _make_session_program(db, sanatorium_id=san.id)
        program.is_active = False
        await db.commit()
        headers = await _customer_headers(client, db)
        resp = await client.post(
            "/api/bookings",
            json={"program_id": str(program.id), "check_in": _FUTURE, "guests": 1},
            headers=headers,
        )
        assert resp.status_code == 404

    async def test_group_size_max_enforced(self, client: AsyncClient, db: AsyncSession):
        san = await make_sanatorium(db, slug="yoga-small")
        program = await _make_session_program(
            db, sanatorium_id=san.id, group_size_max=2
        )
        headers = await _customer_headers(client, db)
        resp = await client.post(
            "/api/bookings",
            json={"program_id": str(program.id), "check_in": _FUTURE, "guests": 5},
            headers=headers,
        )
        assert resp.status_code == 400
        assert "participant" in resp.json()["detail"].lower()

    async def test_program_under_non_approved_sanatorium_returns_400(
        self, client: AsyncClient, db: AsyncSession
    ):
        san = await make_sanatorium(
            db, slug="yoga-pending", status=SanatoriumStatus.PENDING
        )
        program = await _make_session_program(db, sanatorium_id=san.id)
        headers = await _customer_headers(client, db)
        resp = await client.post(
            "/api/bookings",
            json={"program_id": str(program.id), "check_in": _FUTURE, "guests": 1},
            headers=headers,
        )
        assert resp.status_code == 400


class TestSessionBookingCancel:
    async def test_session_booking_can_be_cancelled(
        self, client: AsyncClient, db: AsyncSession
    ):
        san = await make_sanatorium(db, slug="yoga-cancel")
        program = await _make_session_program(db, sanatorium_id=san.id)
        headers = await _customer_headers(client, db)
        created = await client.post(
            "/api/bookings",
            json={"program_id": str(program.id), "check_in": _FUTURE, "guests": 1},
            headers=headers,
        )
        booking_id = created.json()["id"]
        cancel = await client.patch(
            f"/api/bookings/{booking_id}/cancel", headers=headers
        )
        assert cancel.status_code == 200
        assert cancel.json()["status"] == "cancelled"
