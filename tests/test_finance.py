from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking, BookingStatus, BookingType
from app.models.payment import Payment, PaymentMethod, PaymentStatus
from app.models.program import TreatmentProgram
from app.models.user import User, UserRole
from tests.factories import make_sanatorium, make_user


async def _headers(client: AsyncClient, email: str, password: str) -> dict:
    login = await client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _make_program(db: AsyncSession, sanatorium_id: uuid.UUID):
    program = TreatmentProgram(
        sanatorium_id=sanatorium_id,
        name={"en": "Program"},
        description={},
        price=Decimal("100.00"),
        currency="USD",
        instructor_bio={},
        what_to_bring={},
    )
    db.add(program)
    await db.commit()
    await db.refresh(program)
    return program


async def _seed_booking(
    db: AsyncSession,
    *,
    program: TreatmentProgram,
    user: User,
    final_price: str,
    commission: str,
    commission_percent: str,
    is_b2b: bool,
    payment_status: PaymentStatus | None = None,
    booking_status: BookingStatus = BookingStatus.CONFIRMED,
    booking_type: BookingType = BookingType.SESSION,
    check_out: date | None = None,
    agent_discount_percent: str | None = None,
) -> Booking:
    booking = Booking(
        user_id=user.id,
        program_id=program.id,
        booking_type=booking_type,
        check_in=date.today(),
        check_out=check_out or date.today(),
        guests=1,
        rooms_count=1,
        status=booking_status,
        final_price=Decimal(final_price),
        currency="USD",
        is_b2b=is_b2b,
        commission_snapshot=Decimal(commission),
        commission_percent_snapshot=Decimal(commission_percent),
        agent_discount_percent_snapshot=(
            Decimal(agent_discount_percent) if agent_discount_percent else None
        ),
    )
    db.add(booking)
    await db.flush()
    if payment_status is not None:
        db.add(
            Payment(
                booking_id=booking.id,
                method=PaymentMethod.PAYME,
                status=payment_status,
                amount=booking.final_price,
                currency=booking.currency,
            )
        )
    await db.commit()
    await db.refresh(booking)
    return booking


class TestFinanceAccess:
    async def test_customer_cannot_access_finance(
        self, client: AsyncClient, customer_headers: dict
    ):
        resp = await client.get("/api/finance/summary", headers=customer_headers)
        assert resp.status_code == 403

    async def test_anonymous_cannot_access_finance(self, client: AsyncClient):
        resp = await client.get("/api/finance/summary")
        assert resp.status_code == 401


class TestFinanceSummary:
    async def test_super_admin_gets_gross_commission_net_and_payment_totals(
        self,
        client: AsyncClient,
        db: AsyncSession,
        super_admin_headers: dict,
    ):
        san = await make_sanatorium(db, slug="finance-super")
        program = await _make_program(db, san.id)
        agent = await make_user(db, email="finance-agent@test.com", role=UserRole.AGENT)
        customer = await make_user(
            db, email="finance-customer@test.com", role=UserRole.CUSTOMER
        )
        await _seed_booking(
            db,
            program=program,
            user=agent,
            final_price="1000.00",
            commission="50.00",
            commission_percent="5.00",
            is_b2b=True,
            payment_status=PaymentStatus.PAID,
            agent_discount_percent="10.00",
        )
        await _seed_booking(
            db,
            program=program,
            user=customer,
            final_price="500.00",
            commission="60.00",
            commission_percent="12.00",
            is_b2b=False,
            payment_status=PaymentStatus.PENDING,
        )

        resp = await client.get("/api/finance/summary", headers=super_admin_headers)
        assert resp.status_code == 200, resp.text
        item = resp.json()["items"][0]
        assert item["currency"] == "USD"
        assert item["booking_count"] == 2
        assert item["b2b_bookings"] == 1
        assert item["b2c_bookings"] == 1
        assert Decimal(item["gross_amount"]) == Decimal("1500.00")
        assert Decimal(item["paid_amount"]) == Decimal("1000.00")
        assert Decimal(item["pending_payment_amount"]) == Decimal("500.00")
        assert Decimal(item["platform_commission_amount"]) == Decimal("110.00")
        assert Decimal(item["sanatorium_net_amount"]) == Decimal("1390.00")

    async def test_admin_summary_is_limited_to_owned_sanatorium(
        self,
        client: AsyncClient,
        db: AsyncSession,
        admin_user: User,
        admin_headers: dict,
    ):
        own_san = await make_sanatorium(
            db, slug="finance-owned", admin_user_id=admin_user.id
        )
        other_san = await make_sanatorium(db, slug="finance-other")
        own_program = await _make_program(db, own_san.id)
        other_program = await _make_program(db, other_san.id)
        customer = await make_user(db, email="finance-admin-customer@test.com")
        await _seed_booking(
            db,
            program=own_program,
            user=customer,
            final_price="100.00",
            commission="10.00",
            commission_percent="10.00",
            is_b2b=False,
            payment_status=PaymentStatus.PAID,
        )
        await _seed_booking(
            db,
            program=other_program,
            user=customer,
            final_price="900.00",
            commission="90.00",
            commission_percent="10.00",
            is_b2b=False,
            payment_status=PaymentStatus.PAID,
        )

        resp = await client.get("/api/finance/summary", headers=admin_headers)
        assert resp.status_code == 200, resp.text
        item = resp.json()["items"][0]
        assert item["booking_count"] == 1
        assert Decimal(item["gross_amount"]) == Decimal("100.00")
        assert Decimal(item["platform_commission_amount"]) == Decimal("10.00")
        assert Decimal(item["sanatorium_net_amount"]) == Decimal("90.00")

    async def test_agent_summary_hides_internal_commission(
        self, client: AsyncClient, db: AsyncSession
    ):
        agent = await make_user(
            db,
            email="finance-agent-hidden@test.com",
            password="agentpass123",
            role=UserRole.AGENT,
        )
        headers = await _headers(client, agent.email, "agentpass123")
        san = await make_sanatorium(db, slug="finance-agent")
        program = await _make_program(db, san.id)
        await _seed_booking(
            db,
            program=program,
            user=agent,
            final_price="200.00",
            commission="20.00",
            commission_percent="10.00",
            is_b2b=True,
            payment_status=PaymentStatus.PAID,
            agent_discount_percent="5.00",
        )

        resp = await client.get("/api/finance/summary", headers=headers)
        assert resp.status_code == 200, resp.text
        item = resp.json()["items"][0]
        assert Decimal(item["gross_amount"]) == Decimal("200.00")
        assert Decimal(item["paid_amount"]) == Decimal("200.00")
        assert item["platform_commission_amount"] is None
        assert item["sanatorium_net_amount"] is None


class TestFinanceOrders:
    async def test_orders_include_per_booking_finance_for_super_admin(
        self,
        client: AsyncClient,
        db: AsyncSession,
        super_admin_headers: dict,
    ):
        san = await make_sanatorium(db, slug="finance-orders")
        program = await _make_program(db, san.id)
        agent = await make_user(db, email="finance-orders-agent@test.com")
        booking = await _seed_booking(
            db,
            program=program,
            user=agent,
            final_price="300.00",
            commission="30.00",
            commission_percent="10.00",
            is_b2b=True,
            payment_status=PaymentStatus.REFUND_PENDING,
            booking_status=BookingStatus.CANCELLED,
            agent_discount_percent="7.00",
        )

        resp = await client.get("/api/finance/orders", headers=super_admin_headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] == 1
        item = body["items"][0]
        assert item["booking_id"] == str(booking.id)
        assert item["payment_status"] == "refund_pending"
        assert Decimal(item["gross_amount"]) == Decimal("0.00")
        assert Decimal(item["refund_pending_amount"]) == Decimal("300.00")
        assert Decimal(item["platform_commission_amount"]) == Decimal("0.00")

    async def test_orders_filter_by_booking_status(
        self, client: AsyncClient, db: AsyncSession, super_admin_headers: dict
    ):
        san = await make_sanatorium(db, slug="finance-status-filter")
        program = await _make_program(db, san.id)
        customer = await make_user(db, email="status-filter@test.com")
        await _seed_booking(
            db,
            program=program,
            user=customer,
            final_price="100.00",
            commission="10.00",
            commission_percent="10.00",
            is_b2b=False,
            booking_status=BookingStatus.CONFIRMED,
        )
        cancelled = await _seed_booking(
            db,
            program=program,
            user=customer,
            final_price="200.00",
            commission="20.00",
            commission_percent="10.00",
            is_b2b=False,
            booking_status=BookingStatus.CANCELLED,
        )

        resp = await client.get(
            "/api/finance/orders",
            params={"booking_status": "cancelled"},
            headers=super_admin_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["booking_id"] == str(cancelled.id)
        assert body["items"][0]["booking_status"] == "cancelled"

    async def test_orders_filter_by_booking_type(
        self, client: AsyncClient, db: AsyncSession, super_admin_headers: dict
    ):
        san = await make_sanatorium(db, slug="finance-type-filter")
        program = await _make_program(db, san.id)
        customer = await make_user(db, email="type-filter@test.com")
        await _seed_booking(
            db,
            program=program,
            user=customer,
            final_price="100.00",
            commission="10.00",
            commission_percent="10.00",
            is_b2b=False,
            booking_type=BookingType.SESSION,
        )
        room_booking = await _seed_booking(
            db,
            program=program,
            user=customer,
            final_price="150.00",
            commission="15.00",
            commission_percent="10.00",
            is_b2b=False,
            booking_type=BookingType.ROOM,
            check_out=date.today() + timedelta(days=2),
        )

        resp = await client.get(
            "/api/finance/orders",
            params={"booking_type": "room"},
            headers=super_admin_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["booking_id"] == str(room_booking.id)
        assert body["items"][0]["booking_type"] == "room"

    async def test_orders_filter_by_payment_status_matches_displayed_value(
        self, client: AsyncClient, db: AsyncSession, super_admin_headers: dict
    ):
        san = await make_sanatorium(db, slug="finance-payment-filter")
        program = await _make_program(db, san.id)
        customer = await make_user(db, email="payment-filter@test.com")
        paid = await _seed_booking(
            db,
            program=program,
            user=customer,
            final_price="100.00",
            commission="10.00",
            commission_percent="10.00",
            is_b2b=False,
            payment_status=PaymentStatus.PAID,
        )
        await _seed_booking(
            db,
            program=program,
            user=customer,
            final_price="200.00",
            commission="20.00",
            commission_percent="10.00",
            is_b2b=False,
            payment_status=PaymentStatus.PENDING,
        )
        # no payment at all → unpaid
        await _seed_booking(
            db,
            program=program,
            user=customer,
            final_price="300.00",
            commission="30.00",
            commission_percent="10.00",
            is_b2b=False,
        )

        resp = await client.get(
            "/api/finance/orders",
            params={"payment_status": "paid"},
            headers=super_admin_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["booking_id"] == str(paid.id)
        assert body["items"][0]["payment_status"] == "paid"

        resp = await client.get(
            "/api/finance/orders",
            params={"payment_status": "unpaid"},
            headers=super_admin_headers,
        )
        assert resp.json()["total"] == 1
        assert resp.json()["items"][0]["payment_status"] == "unpaid"

    async def test_orders_combine_filters_with_and_semantics(
        self, client: AsyncClient, db: AsyncSession, super_admin_headers: dict
    ):
        san = await make_sanatorium(db, slug="finance-combo-filter")
        program = await _make_program(db, san.id)
        customer = await make_user(db, email="combo-filter@test.com")
        target = await _seed_booking(
            db,
            program=program,
            user=customer,
            final_price="100.00",
            commission="10.00",
            commission_percent="10.00",
            is_b2b=False,
            booking_status=BookingStatus.CONFIRMED,
            payment_status=PaymentStatus.PAID,
        )
        # right status, wrong payment_status → excluded
        await _seed_booking(
            db,
            program=program,
            user=customer,
            final_price="200.00",
            commission="20.00",
            commission_percent="10.00",
            is_b2b=False,
            booking_status=BookingStatus.CONFIRMED,
            payment_status=PaymentStatus.PENDING,
        )

        resp = await client.get(
            "/api/finance/orders",
            params={"booking_status": "confirmed", "payment_status": "paid"},
            headers=super_admin_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["booking_id"] == str(target.id)

    async def test_orders_invalid_enum_returns_422(
        self, client: AsyncClient, super_admin_headers: dict
    ):
        resp = await client.get(
            "/api/finance/orders",
            params={"booking_status": "foo"},
            headers=super_admin_headers,
        )
        assert resp.status_code == 422

    async def test_summary_respects_filters_consistently_with_orders(
        self, client: AsyncClient, db: AsyncSession, super_admin_headers: dict
    ):
        san = await make_sanatorium(db, slug="finance-summary-filter")
        program = await _make_program(db, san.id)
        customer = await make_user(db, email="summary-filter@test.com")
        await _seed_booking(
            db,
            program=program,
            user=customer,
            final_price="100.00",
            commission="10.00",
            commission_percent="10.00",
            is_b2b=False,
            booking_status=BookingStatus.CONFIRMED,
        )
        await _seed_booking(
            db,
            program=program,
            user=customer,
            final_price="400.00",
            commission="40.00",
            commission_percent="10.00",
            is_b2b=False,
            booking_status=BookingStatus.CANCELLED,
        )

        summary = await client.get(
            "/api/finance/summary",
            params={"booking_status": "cancelled"},
            headers=super_admin_headers,
        )
        assert summary.status_code == 200, summary.text
        item = summary.json()["items"][0]
        assert item["booking_count"] == 1
        assert item["cancelled_bookings"] == 1
        assert Decimal(item["cancelled_gross_amount"]) == Decimal("400.00")

        orders = await client.get(
            "/api/finance/orders",
            params={"booking_status": "cancelled"},
            headers=super_admin_headers,
        )
        assert orders.json()["total"] == item["booking_count"]

    async def test_agent_orders_hide_internal_commission(
        self, client: AsyncClient, db: AsyncSession
    ):
        agent = await make_user(
            db,
            email="finance-agent-orders@test.com",
            password="agentpass123",
            role=UserRole.AGENT,
        )
        headers = await _headers(client, agent.email, "agentpass123")
        san = await make_sanatorium(db, slug="finance-agent-orders")
        program = await _make_program(db, san.id)
        await _seed_booking(
            db,
            program=program,
            user=agent,
            final_price="400.00",
            commission="40.00",
            commission_percent="10.00",
            is_b2b=True,
            payment_status=PaymentStatus.PAID,
            agent_discount_percent="4.00",
        )

        resp = await client.get("/api/finance/orders", headers=headers)
        assert resp.status_code == 200, resp.text
        item = resp.json()["items"][0]
        assert item["commission_percent"] is None
        assert item["platform_commission_amount"] is None
        assert item["sanatorium_net_amount"] is None
        assert Decimal(item["agent_discount_percent"]) == Decimal("4.00")
