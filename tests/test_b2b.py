"""Integration tests for /b2b endpoints (agent role)."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking, BookingStatus, BookingType
from app.models.program import TreatmentProgram
from app.models.user import UserRole
from tests.factories import make_sanatorium, make_user

_FUTURE = (date.today() + timedelta(days=20)).isoformat()


async def _agent_headers(
    client: AsyncClient, db: AsyncSession
) -> tuple[dict, uuid.UUID]:
    agent = await make_user(
        db,
        email="agent@test.com",
        password="agentpass123",
        role=UserRole.AGENT,
    )
    login = await client.post(
        "/api/auth/login",
        json={"email": "agent@test.com", "password": "agentpass123"},
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}, agent.id


async def _customer_headers(client: AsyncClient, db: AsyncSession) -> dict:
    await make_user(
        db,
        email="cust-b2b@test.com",
        password="customerpass123",
        role=UserRole.CUSTOMER,
    )
    login = await client.post(
        "/api/auth/login",
        json={"email": "cust-b2b@test.com", "password": "customerpass123"},
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _make_program(db, sanatorium_id, price="100.00"):
    p = TreatmentProgram(
        sanatorium_id=sanatorium_id,
        name={"en": "x"},
        description={},
        price=Decimal(price),
        currency="USD",
        instructor_bio={},
        what_to_bring={},
    )
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return p


async def _seed_booking_for_agent(
    db: AsyncSession,
    agent_id: uuid.UUID,
    program: TreatmentProgram,
    *,
    is_b2b: bool = True,
    status: BookingStatus = BookingStatus.CONFIRMED,
    created_at: datetime | None = None,
    final_price: str = "100.00",
) -> Booking:
    b = Booking(
        user_id=agent_id,
        program_id=program.id,
        booking_type=BookingType.SESSION,
        check_in=date.today(),
        check_out=date.today(),
        guests=1,
        status=status,
        final_price=Decimal(final_price),
        currency="USD",
        is_b2b=is_b2b,
    )
    db.add(b)
    await db.flush()
    if created_at is not None:
        b.created_at = created_at
    await db.commit()
    await db.refresh(b)
    return b


class TestB2BRoleGuard:
    async def test_customer_cannot_call_dashboard(
        self, client: AsyncClient, db: AsyncSession
    ):
        headers = await _customer_headers(client, db)
        resp = await client.get("/api/b2b/dashboard", headers=headers)
        assert resp.status_code == 403

    async def test_anonymous_cannot_call_dashboard(self, client: AsyncClient):
        resp = await client.get("/api/b2b/dashboard")
        assert resp.status_code == 401

    async def test_agent_can_call_dashboard(
        self, client: AsyncClient, db: AsyncSession
    ):
        headers, _ = await _agent_headers(client, db)
        resp = await client.get("/api/b2b/dashboard", headers=headers)
        assert resp.status_code == 200


class TestB2BDashboard:
    async def test_empty_dashboard(self, client: AsyncClient, db: AsyncSession):
        headers, _ = await _agent_headers(client, db)
        resp = await client.get("/api/b2b/dashboard", headers=headers)
        body = resp.json()
        assert body["total_bookings"] == 0
        assert body["bookings_this_month"] == 0
        assert body["bookings_this_year"] == 0
        assert Decimal(body["total_paid"]) == Decimal("0.00")
        assert body["current_year_bookings"] == 0

    async def test_counts_only_own_bookings(
        self, client: AsyncClient, db: AsyncSession
    ):
        headers, agent_id = await _agent_headers(client, db)
        san = await make_sanatorium(db, slug="b2b-1")
        program = await _make_program(db, san.id, price="50.00")
        await _seed_booking_for_agent(db, agent_id, program, final_price="50.00")
        await _seed_booking_for_agent(db, agent_id, program, final_price="50.00")

        # Booking belonging to someone else
        other = await make_user(db, email="someone-else@test.com", role=UserRole.AGENT)
        await _seed_booking_for_agent(db, other.id, program, final_price="999.00")

        resp = await client.get("/api/b2b/dashboard", headers=headers)
        body = resp.json()
        assert body["total_bookings"] == 2
        assert Decimal(body["total_paid"]) == Decimal("100.00")
        assert body["current_year_bookings"] == 2

    async def test_cancelled_excluded_from_total_paid(
        self, client: AsyncClient, db: AsyncSession
    ):
        headers, agent_id = await _agent_headers(client, db)
        san = await make_sanatorium(db, slug="b2b-x")
        program = await _make_program(db, san.id, price="100.00")
        await _seed_booking_for_agent(db, agent_id, program, final_price="100.00")
        await _seed_booking_for_agent(
            db, agent_id, program, status=BookingStatus.CANCELLED, final_price="100.00"
        )
        resp = await client.get("/api/b2b/dashboard", headers=headers)
        body = resp.json()
        # Both bookings count toward total_bookings, but only confirmed counts toward total_paid
        assert body["total_bookings"] == 2
        assert Decimal(body["total_paid"]) == Decimal("100.00")


class TestB2BDiscountStatus:
    async def test_returns_zero_when_no_tiers_configured(
        self, client: AsyncClient, db: AsyncSession
    ):
        headers, _ = await _agent_headers(client, db)
        san = await make_sanatorium(db, slug="b2b-no-tiers")
        resp = await client.get(
            f"/api/b2b/discount-status?sanatorium_id={san.id}",
            headers=headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["current_year_bookings"] == 0
        assert Decimal(body["current_tier_discount_percent"]) == Decimal("0")
        assert body["next_tier"] is None

    async def test_progresses_through_tiers(
        self, client: AsyncClient, db: AsyncSession
    ):
        headers, agent_id = await _agent_headers(client, db)
        san = await make_sanatorium(db, slug="b2b-with-tiers")
        san.agent_discount_tiers = [
            {"min_bookings": 2, "discount_percent": "5"},
            {"min_bookings": 5, "discount_percent": "10"},
        ]
        await db.commit()
        program = await _make_program(db, san.id)

        # Seed 3 confirmed B2B bookings — pushes agent over tier 1
        for _ in range(3):
            await _seed_booking_for_agent(db, agent_id, program, is_b2b=True)

        resp = await client.get(
            f"/api/b2b/discount-status?sanatorium_id={san.id}", headers=headers
        )
        body = resp.json()
        assert body["current_year_bookings"] == 3
        assert Decimal(body["current_tier_discount_percent"]) == Decimal("5")
        assert body["next_tier"]["min_bookings"] == 5
        assert body["next_tier"]["bookings_to_unlock"] == 2

    async def test_non_b2b_bookings_not_counted(
        self, client: AsyncClient, db: AsyncSession
    ):
        headers, agent_id = await _agent_headers(client, db)
        san = await make_sanatorium(db, slug="b2b-mixed")
        san.agent_discount_tiers = [{"min_bookings": 1, "discount_percent": "5"}]
        await db.commit()
        program = await _make_program(db, san.id)

        # Non-B2B booking — must not unlock tier
        await _seed_booking_for_agent(db, agent_id, program, is_b2b=False)

        resp = await client.get(
            f"/api/b2b/discount-status?sanatorium_id={san.id}", headers=headers
        )
        body = resp.json()
        assert body["current_year_bookings"] == 0
        assert Decimal(body["current_tier_discount_percent"]) == Decimal("0")

    async def test_unknown_sanatorium_returns_404(
        self, client: AsyncClient, db: AsyncSession
    ):
        headers, _ = await _agent_headers(client, db)
        resp = await client.get(
            f"/api/b2b/discount-status?sanatorium_id={uuid.uuid4()}",
            headers=headers,
        )
        assert resp.status_code == 404


class TestB2BOrders:
    async def test_orders_empty(self, client: AsyncClient, db: AsyncSession):
        headers, _ = await _agent_headers(client, db)
        resp = await client.get("/api/b2b/orders", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 0

    async def test_orders_returns_own_bookings(
        self, client: AsyncClient, db: AsyncSession
    ):
        headers, agent_id = await _agent_headers(client, db)
        san = await make_sanatorium(db, slug="b2b-orders")
        program = await _make_program(db, san.id, price="200.00")
        b = await _seed_booking_for_agent(
            db, agent_id, program, is_b2b=True, final_price="200.00"
        )
        resp = await client.get("/api/b2b/orders", headers=headers)
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["booking_id"] == str(b.id)
        assert Decimal(body["items"][0]["price_paid"]) == Decimal("200.00")

    async def test_orders_pagination(self, client: AsyncClient, db: AsyncSession):
        headers, agent_id = await _agent_headers(client, db)
        san = await make_sanatorium(db, slug="b2b-paged")
        program = await _make_program(db, san.id)
        for _ in range(3):
            await _seed_booking_for_agent(db, agent_id, program)
        resp = await client.get("/api/b2b/orders?limit=2&offset=0", headers=headers)
        body = resp.json()
        assert body["total"] == 3
        assert len(body["items"]) == 2

    async def test_orders_excludes_other_agents(
        self, client: AsyncClient, db: AsyncSession
    ):
        headers, agent_id = await _agent_headers(client, db)
        san = await make_sanatorium(db, slug="b2b-isolated")
        program = await _make_program(db, san.id)
        await _seed_booking_for_agent(db, agent_id, program)

        other = await make_user(db, email="other-ag@test.com", role=UserRole.AGENT)
        await _seed_booking_for_agent(db, other.id, program)

        resp = await client.get("/api/b2b/orders", headers=headers)
        body = resp.json()
        assert body["total"] == 1
