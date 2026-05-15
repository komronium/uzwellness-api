"""Integration tests for rooms, availability, exchange rates, and room search."""
from datetime import datetime, timezone

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.room import ExchangeRate, Room
from app.models.sanatorium import Sanatorium, SanatoriumStatus
from app.models.user import User, UserRole
from tests.factories import make_sanatorium, make_user


async def make_room(
    db: AsyncSession,
    *,
    sanatorium: Sanatorium,
    name: str = "Standard",
    capacity: int = 2,
    base_price: str = "100.00",
    base_currency: str = "USD",
    min_nights: int = 1,
    markup_percent: str = "0",
    is_active: bool = True,
) -> Room:
    from decimal import Decimal

    room = Room(
        sanatorium_id=sanatorium.id,
        name={"en": name},
        capacity=capacity,
        base_price=Decimal(base_price),
        base_currency=base_currency,
        min_nights=min_nights,
        markup_percent=Decimal(markup_percent),
        is_active=is_active,
    )
    db.add(room)
    await db.commit()
    await db.refresh(room)
    return room


async def make_exchange_rate(
    db: AsyncSession, *, pair: str = "USD_UZS", rate: str = "12500"
) -> ExchangeRate:
    from decimal import Decimal

    er = ExchangeRate(
        pair=pair,
        rate=Decimal(rate),
        valid_from=datetime.now(tz=timezone.utc),
    )
    db.add(er)
    await db.commit()
    await db.refresh(er)
    return er


# ── Room CRUD ──────────────────────────────────────────────────────────────

class TestRoomCRUD:
    async def test_admin_creates_room_for_own_sanatorium(
        self, client: AsyncClient, db: AsyncSession, admin_user: User, admin_headers
    ):
        san = await make_sanatorium(
            db, status=SanatoriumStatus.APPROVED, admin_user_id=admin_user.id
        )
        resp = await client.post(
            "/api/rooms",
            json={
                "sanatorium_id": str(san.id),
                "name": {"en": "Deluxe"},
                "capacity": 2,
                "base_price": "150.00",
                "base_currency": "USD",
                "min_nights": 2,
            },
            headers=admin_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["capacity"] == 2
        assert data["base_currency"] == "USD"
        assert data["final_price"] == "150.00"

    async def test_admin_cannot_create_room_for_other_sanatorium(
        self, client: AsyncClient, db: AsyncSession, admin_user: User, admin_headers
    ):
        other_admin = await make_user(db, email="other@test.com", role=UserRole.ADMIN)
        san = await make_sanatorium(
            db, status=SanatoriumStatus.APPROVED, admin_user_id=other_admin.id
        )
        resp = await client.post(
            "/api/rooms",
            json={
                "sanatorium_id": str(san.id),
                "name": {"en": "Deluxe"},
                "capacity": 2,
                "base_price": "100.00",
                "base_currency": "USD",
            },
            headers=admin_headers,
        )
        assert resp.status_code == 403

    async def test_customer_cannot_create_room(
        self, client: AsyncClient, db: AsyncSession, admin_user: User, customer_headers
    ):
        san = await make_sanatorium(db, admin_user_id=admin_user.id)
        resp = await client.post(
            "/api/rooms",
            json={
                "sanatorium_id": str(san.id),
                "name": {"en": "Deluxe"},
                "capacity": 2,
                "base_price": "100.00",
                "base_currency": "USD",
            },
            headers=customer_headers,
        )
        assert resp.status_code == 403

    async def test_list_rooms_public(
        self, client: AsyncClient, db: AsyncSession
    ):
        san = await make_sanatorium(db, status=SanatoriumStatus.APPROVED)
        await make_room(db, sanatorium=san)
        resp = await client.get(f"/api/rooms?sanatorium_id={san.id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1

    async def test_super_admin_sets_markup_percent(
        self,
        client: AsyncClient,
        db: AsyncSession,
        admin_user: User,
        super_admin_headers,
    ):
        san = await make_sanatorium(db, admin_user_id=admin_user.id)
        room = await make_room(db, sanatorium=san, base_price="100.00")
        resp = await client.patch(
            f"/api/rooms/{room.id}",
            json={"markup_percent": "20.00"},
            headers=super_admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["markup_percent"] == "20.00"
        assert resp.json()["final_price"] == "120.00"

    async def test_admin_cannot_set_markup_percent(
        self,
        client: AsyncClient,
        db: AsyncSession,
        admin_user: User,
        admin_headers,
    ):
        san = await make_sanatorium(db, admin_user_id=admin_user.id)
        room = await make_room(db, sanatorium=san)
        resp = await client.patch(
            f"/api/rooms/{room.id}",
            json={"markup_percent": "15.00"},
            headers=admin_headers,
        )
        assert resp.status_code == 403


# ── Availability ───────────────────────────────────────────────────────────

class TestAvailability:
    async def test_bulk_create(
        self,
        client: AsyncClient,
        db: AsyncSession,
        admin_user: User,
        admin_headers,
    ):
        san = await make_sanatorium(
            db, status=SanatoriumStatus.APPROVED, admin_user_id=admin_user.id
        )
        room = await make_room(db, sanatorium=san)
        resp = await client.post(
            f"/api/rooms/{room.id}/availability",
            json={
                "date_from": "2026-06-01",
                "date_to": "2026-06-08",
                "units_total": 5,
            },
            headers=admin_headers,
        )
        assert resp.status_code == 201
        assert len(resp.json()) == 7  # 7 nights: Jun 1–7

    async def test_get_availability(
        self,
        client: AsyncClient,
        db: AsyncSession,
        admin_user: User,
        admin_headers,
    ):
        san = await make_sanatorium(
            db, status=SanatoriumStatus.APPROVED, admin_user_id=admin_user.id
        )
        room = await make_room(db, sanatorium=san)
        await client.post(
            f"/api/rooms/{room.id}/availability",
            json={"date_from": "2026-07-01", "date_to": "2026-07-04", "units_total": 3},
            headers=admin_headers,
        )
        resp = await client.get(
            f"/api/rooms/{room.id}/availability?from=2026-07-01&to=2026-07-04"
        )
        assert resp.status_code == 200
        dates = [r["date"] for r in resp.json()]
        assert dates == ["2026-07-01", "2026-07-02", "2026-07-03"]

    async def test_no_overwrite_by_default(
        self,
        client: AsyncClient,
        db: AsyncSession,
        admin_user: User,
        admin_headers,
    ):
        san = await make_sanatorium(db, admin_user_id=admin_user.id)
        room = await make_room(db, sanatorium=san)
        await client.post(
            f"/api/rooms/{room.id}/availability",
            json={"date_from": "2026-08-01", "date_to": "2026-08-03", "units_total": 10},
            headers=admin_headers,
        )
        await client.post(
            f"/api/rooms/{room.id}/availability",
            json={"date_from": "2026-08-01", "date_to": "2026-08-03", "units_total": 1},
            headers=admin_headers,
        )
        # units should still be 10, not overwritten
        resp = await client.get(
            f"/api/rooms/{room.id}/availability?from=2026-08-01&to=2026-08-03"
        )
        for row in resp.json():
            assert row["units_total"] == 10

    async def test_overwrite_flag(
        self,
        client: AsyncClient,
        db: AsyncSession,
        admin_user: User,
        admin_headers,
    ):
        san = await make_sanatorium(db, admin_user_id=admin_user.id)
        room = await make_room(db, sanatorium=san)
        for units in (10, 2):
            await client.post(
                f"/api/rooms/{room.id}/availability",
                json={
                    "date_from": "2026-09-01",
                    "date_to": "2026-09-03",
                    "units_total": units,
                    "overwrite": True,
                },
                headers=admin_headers,
            )
        resp = await client.get(
            f"/api/rooms/{room.id}/availability?from=2026-09-01&to=2026-09-03"
        )
        for row in resp.json():
            assert row["units_total"] == 2


# ── Room search ────────────────────────────────────────────────────────────

class TestRoomSearch:
    async def _setup(self, db, admin_user, client, admin_headers):
        san = await make_sanatorium(
            db, status=SanatoriumStatus.APPROVED, admin_user_id=admin_user.id
        )
        room = await make_room(db, sanatorium=san, capacity=2, min_nights=1)
        await client.post(
            f"/api/rooms/{room.id}/availability",
            json={"date_from": "2026-10-01", "date_to": "2026-10-08", "units_total": 3},
            headers=admin_headers,
        )
        return san, room

    async def test_finds_available_room(
        self, client, db, admin_user, admin_headers
    ):
        san, room = await self._setup(db, admin_user, client, admin_headers)
        resp = await client.get(
            "/api/rooms/search?check_in=2026-10-02&check_out=2026-10-05&guests=2"
        )
        assert resp.status_code == 200
        ids = [r["id"] for r in resp.json()]
        assert str(room.id) in ids

    async def test_excludes_room_with_missing_dates(
        self, client, db, admin_user, admin_headers
    ):
        san, room = await self._setup(db, admin_user, client, admin_headers)
        # availability ends Oct 7; request through Oct 10 — not fully covered
        resp = await client.get(
            "/api/rooms/search?check_in=2026-10-06&check_out=2026-10-10&guests=2"
        )
        ids = [r["id"] for r in resp.json()]
        assert str(room.id) not in ids

    async def test_excludes_room_with_insufficient_capacity(
        self, client, db, admin_user, admin_headers
    ):
        san, room = await self._setup(db, admin_user, client, admin_headers)
        resp = await client.get(
            "/api/rooms/search?check_in=2026-10-02&check_out=2026-10-05&guests=3"
        )
        ids = [r["id"] for r in resp.json()]
        assert str(room.id) not in ids

    async def test_check_out_must_be_after_check_in(self, client, db):
        resp = await client.get(
            "/api/rooms/search?check_in=2026-10-05&check_out=2026-10-02&guests=1"
        )
        assert resp.status_code == 400


# ── Exchange rates ─────────────────────────────────────────────────────────

class TestExchangeRates:
    async def test_super_admin_upserts_rate(
        self, client, super_admin_headers
    ):
        resp = await client.patch(
            "/api/exchange-rates",
            json={
                "pair": "USD_UZS",
                "rate": "12700.000000",
                "valid_from": "2026-05-01T00:00:00Z",
            },
            headers=super_admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["pair"] == "USD_UZS"

    async def test_upsert_updates_existing(self, client, super_admin_headers):
        for rate in ("12000.000000", "12700.000000"):
            resp = await client.patch(
                "/api/exchange-rates",
                json={"pair": "USD_UZS", "rate": rate, "valid_from": "2026-05-01T00:00:00Z"},
                headers=super_admin_headers,
            )
            assert resp.status_code == 200
        rates = await client.get("/api/exchange-rates")
        uzs_entries = [r for r in rates.json() if r["pair"] == "USD_UZS"]
        assert len(uzs_entries) == 1
        assert uzs_entries[0]["rate"] == "12700.000000"

    async def test_public_can_list(self, client):
        resp = await client.get("/api/exchange-rates")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_customer_cannot_upsert(self, client, customer_headers):
        resp = await client.patch(
            "/api/exchange-rates",
            json={"pair": "USD_UZS", "rate": "12000.000000", "valid_from": "2026-05-01T00:00:00Z"},
            headers=customer_headers,
        )
        assert resp.status_code == 403

    async def test_room_read_includes_converted_prices(
        self, client, db, admin_user, admin_headers, super_admin_headers
    ):
        await client.patch(
            "/api/exchange-rates",
            json={"pair": "USD_UZS", "rate": "12500.000000", "valid_from": "2026-05-01T00:00:00Z"},
            headers=super_admin_headers,
        )
        san = await make_sanatorium(db, admin_user_id=admin_user.id)
        room = await make_room(db, sanatorium=san, base_price="1.00", base_currency="USD")
        resp = await client.get(f"/api/rooms/{room.id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["final_price_uzs"] == "12500.00"
        assert body["final_price_usd"] == "1.00"
