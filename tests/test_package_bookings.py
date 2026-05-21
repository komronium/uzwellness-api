"""Integration tests for PACKAGE bookings — admin-fixed room, customer picks
just the package + dates."""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.package import Package
from app.models.sanatorium import Sanatorium, SanatoriumStatus
from app.models.user import UserRole
from tests.factories import make_sanatorium, make_user
from tests.test_availability import make_room

_FUTURE = (date.today() + timedelta(days=30)).isoformat()
_FUTURE_DATE = date.today() + timedelta(days=30)


async def _make_room_for(db: AsyncSession, sanatorium: Sanatorium, **kw):
    kw.setdefault("base_currency", "USD")
    kw.setdefault("inventory_count", 5)
    return await make_room(db, sanatorium=sanatorium, **kw)


async def _make_package(
    db: AsyncSession,
    sanatorium: Sanatorium,
    *,
    room=None,
    base_price: str = "1290.00",
    currency: str = "USD",
    duration_nights: int = 5,
    is_active: bool = True,
) -> Package:
    if room is None:
        room = await _make_room_for(db, sanatorium, base_currency=currency)
    package = Package(
        slug=f"pkg-{uuid.uuid4().hex[:8]}",
        title={"uz": "Sayohat", "ru": "Путешествие", "en": "Journey"},
        description={"uz": "...", "ru": "...", "en": "..."},
        duration_nights=duration_nights,
        base_price=Decimal(base_price),
        currency=currency,
        sanatorium_id=sanatorium.id,
        room_id=room.id,
        is_active=is_active,
    )
    db.add(package)
    await db.commit()
    await db.refresh(package)
    return package


@pytest.fixture
async def package_sanatorium(db: AsyncSession):
    return await make_sanatorium(
        db,
        slug="pkg-host",
        name="Pkg Host",
        status=SanatoriumStatus.APPROVED,
    )


async def _customer_headers(client: AsyncClient, db: AsyncSession) -> dict:
    await make_user(
        db,
        email="customer-pkg@test.com",
        password="customerpass123",
        role=UserRole.CUSTOMER,
    )
    login = await client.post(
        "/api/auth/login",
        json={"email": "customer-pkg@test.com", "password": "customerpass123"},
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


class TestPackageBookingHappyPath:
    async def test_book_package_for_one_guest(
        self, client: AsyncClient, db: AsyncSession, package_sanatorium
    ):
        room = await _make_room_for(db, package_sanatorium)
        package = await _make_package(
            db, package_sanatorium, room=room, base_price="1290.00"
        )
        headers = await _customer_headers(client, db)
        resp = await client.post(
            "/api/bookings",
            json={
                "package_id": str(package.id),
                "check_in": _FUTURE,
                "guests": 1,
            },
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["booking_type"] == "package"
        assert body["package_id"] == str(package.id)
        assert body["room_id"] == str(room.id)
        assert body["final_price"] == "1290.00"
        assert body["currency"] == "USD"

    async def test_price_scales_with_guests(
        self, client: AsyncClient, db: AsyncSession, package_sanatorium
    ):
        room = await _make_room_for(db, package_sanatorium, capacity=4)
        package = await _make_package(
            db, package_sanatorium, room=room, base_price="500.00"
        )
        headers = await _customer_headers(client, db)
        resp = await client.post(
            "/api/bookings",
            json={
                "package_id": str(package.id),
                "check_in": _FUTURE,
                "guests": 3,
            },
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["final_price"] == "1500.00"

    async def test_check_out_defaults_to_duration_nights(
        self, client: AsyncClient, db: AsyncSession, package_sanatorium
    ):
        package = await _make_package(
            db, package_sanatorium, duration_nights=7
        )
        headers = await _customer_headers(client, db)
        resp = await client.post(
            "/api/bookings",
            json={
                "package_id": str(package.id),
                "check_in": _FUTURE,
                "guests": 1,
            },
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        expected = (_FUTURE_DATE + timedelta(days=7)).isoformat()
        assert resp.json()["check_out"] == expected


class TestPackageBookingErrors:
    async def test_inactive_package_returns_404(
        self, client: AsyncClient, db: AsyncSession, package_sanatorium
    ):
        package = await _make_package(
            db, package_sanatorium, is_active=False
        )
        headers = await _customer_headers(client, db)
        resp = await client.post(
            "/api/bookings",
            json={
                "package_id": str(package.id),
                "check_in": _FUTURE,
                "guests": 1,
            },
            headers=headers,
        )
        assert resp.status_code == 404

    async def test_unapproved_sanatorium_blocks_booking(
        self, client: AsyncClient, db: AsyncSession
    ):
        pending = await make_sanatorium(
            db, slug="pkg-pending", status=SanatoriumStatus.PENDING
        )
        package = await _make_package(db, pending)
        headers = await _customer_headers(client, db)
        resp = await client.post(
            "/api/bookings",
            json={
                "package_id": str(package.id),
                "check_in": _FUTURE,
                "guests": 1,
            },
            headers=headers,
        )
        assert resp.status_code == 400

    async def test_cannot_combine_room_and_package(
        self, client: AsyncClient, db: AsyncSession, package_sanatorium
    ):
        package = await _make_package(db, package_sanatorium)
        headers = await _customer_headers(client, db)
        resp = await client.post(
            "/api/bookings",
            json={
                "package_id": str(package.id),
                "room_id": str(uuid.uuid4()),
                "check_in": _FUTURE,
                "guests": 1,
            },
            headers=headers,
        )
        assert resp.status_code == 422

    async def test_check_out_mismatch_rejected(
        self, client: AsyncClient, db: AsyncSession, package_sanatorium
    ):
        package = await _make_package(
            db, package_sanatorium, duration_nights=5
        )
        headers = await _customer_headers(client, db)
        wrong_out = (_FUTURE_DATE + timedelta(days=3)).isoformat()
        resp = await client.post(
            "/api/bookings",
            json={
                "package_id": str(package.id),
                "check_in": _FUTURE,
                "check_out": wrong_out,
                "guests": 1,
            },
            headers=headers,
        )
        assert resp.status_code == 400


class TestPackageBookingInventory:
    async def test_decrements_availability(
        self, client: AsyncClient, db: AsyncSession, package_sanatorium
    ):
        from sqlalchemy import select

        from app.models.availability import RoomAvailability

        room = await _make_room_for(db, package_sanatorium, inventory_count=2)
        package = await _make_package(
            db, package_sanatorium, room=room, duration_nights=2
        )
        headers = await _customer_headers(client, db)
        resp = await client.post(
            "/api/bookings",
            json={
                "package_id": str(package.id),
                "check_in": _FUTURE,
                "guests": 1,
            },
            headers=headers,
        )
        assert resp.status_code == 201, resp.text

        rows = (
            await db.execute(
                select(RoomAvailability).where(RoomAvailability.room_id == room.id)
            )
        ).scalars().all()
        assert len(rows) == 2
        assert all(r.units_booked == 1 for r in rows)


class TestPackageBookingCancel:
    async def test_customer_can_cancel_package_booking(
        self, client: AsyncClient, db: AsyncSession, package_sanatorium
    ):
        from sqlalchemy import select

        from app.models.availability import RoomAvailability

        room = await _make_room_for(db, package_sanatorium, inventory_count=2)
        package = await _make_package(
            db, package_sanatorium, room=room, duration_nights=2
        )
        headers = await _customer_headers(client, db)
        created = await client.post(
            "/api/bookings",
            json={
                "package_id": str(package.id),
                "check_in": _FUTURE,
                "guests": 1,
            },
            headers=headers,
        )
        assert created.status_code == 201, created.text
        booking_id = created.json()["id"]
        resp = await client.patch(
            f"/api/bookings/{booking_id}/cancel", headers=headers
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"

        rows = (
            await db.execute(
                select(RoomAvailability).where(RoomAvailability.room_id == room.id)
            )
        ).scalars().all()
        assert all(r.units_booked == 0 for r in rows)
