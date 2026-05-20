"""Integration tests for PACKAGE bookings (curated multi-day journeys)."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.package import Package
from app.models.sanatorium import SanatoriumStatus
from app.models.user import UserRole
from tests.factories import make_sanatorium, make_user

_FUTURE = (date.today() + timedelta(days=30)).isoformat()
_FUTURE_DATE = date.today() + timedelta(days=30)


async def _make_package(
    db: AsyncSession,
    *,
    base_price: str = "1290.00",
    currency: str = "USD",
    duration_nights: int = 5,
    sanatorium_id=None,
    is_active: bool = True,
) -> Package:
    package = Package(
        slug=f"pkg-{base_price}-{duration_nights}-{int(date.today().toordinal())}",
        title={"uz": "Sayohat", "ru": "Путешествие", "en": "Journey"},
        description={"uz": "...", "ru": "...", "en": "..."},
        duration_nights=duration_nights,
        base_price=Decimal(base_price),
        currency=currency,
        sanatorium_id=sanatorium_id,
        is_active=is_active,
    )
    db.add(package)
    await db.commit()
    await db.refresh(package)
    return package


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
        self, client: AsyncClient, db: AsyncSession
    ):
        package = await _make_package(db, base_price="1290.00")
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
        assert body["final_price"] == "1290.00"
        assert body["currency"] == "USD"

    async def test_price_scales_with_guests(
        self, client: AsyncClient, db: AsyncSession
    ):
        package = await _make_package(db, base_price="500.00")
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
        assert resp.status_code == 201
        assert resp.json()["final_price"] == "1500.00"

    async def test_check_out_defaults_to_duration_nights(
        self, client: AsyncClient, db: AsyncSession
    ):
        package = await _make_package(db, duration_nights=7)
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
        assert resp.status_code == 201
        expected = (_FUTURE_DATE + timedelta(days=7)).isoformat()
        assert resp.json()["check_out"] == expected

    async def test_book_package_with_sanatorium_link(
        self, client: AsyncClient, db: AsyncSession
    ):
        san = await make_sanatorium(
            db, slug="pkg-linked", status=SanatoriumStatus.APPROVED
        )
        package = await _make_package(db, sanatorium_id=san.id)
        headers = await _customer_headers(client, db)
        resp = await client.post(
            "/api/bookings",
            json={
                "package_id": str(package.id),
                "check_in": _FUTURE,
                "guests": 2,
            },
            headers=headers,
        )
        assert resp.status_code == 201


class TestPackageBookingErrors:
    async def test_inactive_package_returns_404(
        self, client: AsyncClient, db: AsyncSession
    ):
        package = await _make_package(db, is_active=False)
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
        san = await make_sanatorium(
            db, slug="pkg-pending", status=SanatoriumStatus.PENDING
        )
        package = await _make_package(db, sanatorium_id=san.id)
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
        self, client: AsyncClient, db: AsyncSession
    ):
        import uuid
        package = await _make_package(db)
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


class TestPackageBookingCancel:
    async def test_customer_can_cancel_package_booking(
        self, client: AsyncClient, db: AsyncSession
    ):
        package = await _make_package(db)
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
        booking_id = created.json()["id"]
        resp = await client.patch(
            f"/api/bookings/{booking_id}/cancel", headers=headers
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"
