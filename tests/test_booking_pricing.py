"""Integration tests for commission snapshot and B2B tier discount."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking
from app.models.program import TreatmentProgram
from app.models.sanatorium import SanatoriumStatus
from app.models.user import UserRole
from tests.factories import make_sanatorium, make_user

_FUTURE = (date.today() + timedelta(days=15)).isoformat()


async def _agent_headers(
    client: AsyncClient, db: AsyncSession
) -> tuple[dict, uuid.UUID]:
    agent = await make_user(
        db,
        email="agent-price@test.com",
        password="agentpass123",
        role=UserRole.AGENT,
    )
    login = await client.post(
        "/api/auth/login",
        json={"email": "agent-price@test.com", "password": "agentpass123"},
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}, agent.id


async def _customer_headers(client: AsyncClient, db: AsyncSession) -> dict:
    await make_user(
        db,
        email="cust-price@test.com",
        password="customerpass123",
        role=UserRole.CUSTOMER,
    )
    login = await client.post(
        "/api/auth/login",
        json={"email": "cust-price@test.com", "password": "customerpass123"},
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _seed_program(db, sanatorium_id, price="100.00"):
    p = TreatmentProgram(
        sanatorium_id=sanatorium_id,
        name={"en": "Program"},
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


class TestCommissionSnapshot:
    async def test_b2c_uses_platform_commission(
        self, client: AsyncClient, db: AsyncSession
    ):
        san = await make_sanatorium(db, slug="comm-1", status=SanatoriumStatus.APPROVED)
        san.platform_commission_percent = Decimal("10")
        san.b2b_commission_percent = Decimal("5")
        await db.commit()
        program = await _seed_program(db, san.id, price="100.00")
        headers = await _customer_headers(client, db)
        resp = await client.post(
            "/api/bookings",
            json={"program_id": str(program.id), "check_in": _FUTURE, "guests": 1},
            headers=headers,
        )
        booking_id = uuid.UUID(resp.json()["id"])
        b = (
            await db.execute(select(Booking).where(Booking.id == booking_id))
        ).scalar_one()
        await db.refresh(b)
        assert b.is_b2b is False
        assert b.commission_percent_snapshot == Decimal("10.00")
        assert b.commission_snapshot == Decimal("10.00")

    async def test_b2b_uses_b2b_commission(self, client: AsyncClient, db: AsyncSession):
        san = await make_sanatorium(db, slug="comm-2", status=SanatoriumStatus.APPROVED)
        san.platform_commission_percent = Decimal("10")
        san.b2b_commission_percent = Decimal("5")
        await db.commit()
        program = await _seed_program(db, san.id, price="200.00")
        headers, _ = await _agent_headers(client, db)
        resp = await client.post(
            "/api/bookings",
            json={"program_id": str(program.id), "check_in": _FUTURE, "guests": 1},
            headers=headers,
        )
        booking_id = uuid.UUID(resp.json()["id"])
        b = (
            await db.execute(select(Booking).where(Booking.id == booking_id))
        ).scalar_one()
        await db.refresh(b)
        assert b.is_b2b is True
        assert b.commission_percent_snapshot == Decimal("5.00")
        assert b.commission_snapshot == Decimal("10.00")  # 5% of 200


class TestAgentTierDiscount:
    async def test_tier_discount_applied_to_final_price(
        self, client: AsyncClient, db: AsyncSession
    ):
        san = await make_sanatorium(db, slug="tier-1", status=SanatoriumStatus.APPROVED)
        # Configure tier: at >=1 booking, agent gets 10% off
        san.agent_discount_tiers = [{"min_bookings": 1, "discount_percent": "10"}]
        await db.commit()
        program = await _seed_program(db, san.id, price="100.00")
        headers, _ = await _agent_headers(client, db)

        # First booking — agent is below threshold (count includes only PRIOR confirmed
        # B2B bookings, so first one gets no discount)
        first = await client.post(
            "/api/bookings",
            json={"program_id": str(program.id), "check_in": _FUTURE, "guests": 1},
            headers=headers,
        )
        assert first.status_code == 201
        assert first.json()["final_price"] == "100.00"

        # Second booking — now the agent already has 1 prior confirmed booking
        second = await client.post(
            "/api/bookings",
            json={"program_id": str(program.id), "check_in": _FUTURE, "guests": 1},
            headers=headers,
        )
        assert second.status_code == 201
        assert second.json()["final_price"] == "90.00"

    async def test_tier_discount_snapshot_persisted(
        self, client: AsyncClient, db: AsyncSession
    ):
        san = await make_sanatorium(db, slug="tier-2", status=SanatoriumStatus.APPROVED)
        san.agent_discount_tiers = [{"min_bookings": 0, "discount_percent": "15"}]
        await db.commit()
        program = await _seed_program(db, san.id, price="100.00")
        headers, _ = await _agent_headers(client, db)
        resp = await client.post(
            "/api/bookings",
            json={"program_id": str(program.id), "check_in": _FUTURE, "guests": 1},
            headers=headers,
        )
        booking_id = uuid.UUID(resp.json()["id"])
        b = (
            await db.execute(select(Booking).where(Booking.id == booking_id))
        ).scalar_one()
        await db.refresh(b)
        assert b.agent_discount_percent_snapshot == Decimal("15.00")
        assert b.final_price == Decimal("85.00")

    async def test_customer_does_not_trigger_tier(
        self, client: AsyncClient, db: AsyncSession
    ):
        san = await make_sanatorium(db, slug="tier-3")
        san.agent_discount_tiers = [{"min_bookings": 0, "discount_percent": "50"}]
        await db.commit()
        program = await _seed_program(db, san.id, price="100.00")
        headers = await _customer_headers(client, db)
        resp = await client.post(
            "/api/bookings",
            json={"program_id": str(program.id), "check_in": _FUTURE, "guests": 1},
            headers=headers,
        )
        # Customer is not B2B → no tier discount applied
        assert resp.json()["final_price"] == "100.00"


class TestB2BClientPriceRemoved:
    async def test_b2b_client_price_is_ignored_and_not_exposed_for_agent(
        self, client: AsyncClient, db: AsyncSession
    ):
        san = await make_sanatorium(db, slug="cp-1")
        program = await _seed_program(db, san.id, price="100.00")
        headers, _ = await _agent_headers(client, db)
        resp = await client.post(
            "/api/bookings",
            json={
                "program_id": str(program.id),
                "check_in": _FUTURE,
                "guests": 1,
                "b2b_client_price": "150.00",
            },
            headers=headers,
        )
        body = resp.json()
        assert resp.status_code == 201
        assert "b2b_client_price" not in body
        assert "b2b_commission" not in body

    async def test_b2b_client_price_is_ignored_and_not_exposed_for_customer(
        self, client: AsyncClient, db: AsyncSession
    ):
        san = await make_sanatorium(db, slug="cp-2")
        program = await _seed_program(db, san.id, price="100.00")
        headers = await _customer_headers(client, db)
        resp = await client.post(
            "/api/bookings",
            json={
                "program_id": str(program.id),
                "check_in": _FUTURE,
                "guests": 1,
                "b2b_client_price": "50.00",
            },
            headers=headers,
        )
        body = resp.json()
        assert resp.status_code == 201
        assert "b2b_client_price" not in body
        assert "b2b_commission" not in body
