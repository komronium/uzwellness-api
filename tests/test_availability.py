"""Integration tests for rooms, availability, exchange rates, and room search."""
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sanatorium import SanatoriumStatus
from app.models.user import User, UserRole
from tests.factories import make_exchange_rate, make_room, make_sanatorium, make_user


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
                "name": {"uz": "Deluxe", "ru": "Делюкс", "en": "Deluxe"},
                "description": {"uz": "Yaxshi xona", "ru": "Хорошая комната", "en": "Nice room"},
                "capacity": 2,
                "inventory_count": 3,
                "base_price": "150.00",
                "base_currency": "USD",
                "min_nights": 2,
            },
            headers=admin_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["capacity"] == 2
        assert data["inventory_count"] == 3
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
                "name": {"uz": "Deluxe", "ru": "Делюкс", "en": "Deluxe"},
                "description": {"uz": "Yaxshi xona", "ru": "Хорошая комната", "en": "Nice room"},
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
                "name": {"uz": "Deluxe", "ru": "Делюкс", "en": "Deluxe"},
                "description": {"uz": "Yaxshi xona", "ru": "Хорошая комната", "en": "Nice room"},
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

    async def test_currency_change_blocked_when_packages_link(
        self,
        client: AsyncClient,
        db: AsyncSession,
        admin_user: User,
        super_admin_headers,
    ):
        from decimal import Decimal

        from app.models.package import Package

        san = await make_sanatorium(db, admin_user_id=admin_user.id)
        room = await make_room(db, sanatorium=san, base_currency="USD")
        pkg = Package(
            slug="pkg-locked",
            title={"uz": "P", "ru": "P", "en": "P"},
            description={"uz": "d", "ru": "d", "en": "d"},
            duration_nights=3,
            base_price=Decimal("100.00"),
            currency="USD",
            sanatorium_id=san.id,
            room_id=room.id,
        )
        db.add(pkg)
        await db.commit()

        resp = await client.patch(
            f"/api/rooms/{room.id}",
            json={"base_currency": "UZS"},
            headers=super_admin_headers,
        )
        assert resp.status_code == 409
        assert "package" in resp.json()["detail"].lower()


# ── Availability (lazy materialization) ────────────────────────────────────

class TestAvailability:
    async def test_lazy_returns_full_inventory_when_no_rows(
        self,
        client: AsyncClient,
        db: AsyncSession,
        admin_user: User,
    ):
        san = await make_sanatorium(
            db, status=SanatoriumStatus.APPROVED, admin_user_id=admin_user.id
        )
        room = await make_room(db, sanatorium=san, inventory_count=5)
        resp = await client.get(
            f"/api/rooms/{room.id}/availability?from=2026-07-01&to=2026-07-04"
        )
        assert resp.status_code == 200
        rows = resp.json()
        assert len(rows) == 3
        for row in rows:
            assert row["inventory_count"] == 5
            assert row["units_blocked"] == 0
            assert row["units_booked"] == 0
            assert row["units_available"] == 5

    async def test_block_range_creates_exception_rows(
        self,
        client: AsyncClient,
        db: AsyncSession,
        admin_user: User,
        admin_headers,
    ):
        san = await make_sanatorium(
            db, status=SanatoriumStatus.APPROVED, admin_user_id=admin_user.id
        )
        room = await make_room(db, sanatorium=san, inventory_count=5)
        resp = await client.post(
            f"/api/rooms/{room.id}/availability/block",
            json={
                "date_from": "2026-06-01",
                "date_to": "2026-06-04",
                "units_blocked": 2,
            },
            headers=admin_headers,
        )
        assert resp.status_code == 201
        rows = resp.json()
        assert len(rows) == 3
        for row in rows:
            assert row["units_blocked"] == 2
            assert row["units_available"] == 3

    async def test_block_exceeding_inventory_returns_409(
        self,
        client: AsyncClient,
        db: AsyncSession,
        admin_user: User,
        admin_headers,
    ):
        san = await make_sanatorium(
            db, status=SanatoriumStatus.APPROVED, admin_user_id=admin_user.id
        )
        room = await make_room(db, sanatorium=san, inventory_count=3)
        resp = await client.post(
            f"/api/rooms/{room.id}/availability/block",
            json={
                "date_from": "2026-06-01",
                "date_to": "2026-06-02",
                "units_blocked": 5,
            },
            headers=admin_headers,
        )
        assert resp.status_code == 409


# ── Room search ────────────────────────────────────────────────────────────

class TestRoomSearch:
    async def test_finds_available_room(
        self, client, db, admin_user, admin_headers
    ):
        san = await make_sanatorium(
            db, status=SanatoriumStatus.APPROVED, admin_user_id=admin_user.id
        )
        room = await make_room(
            db, sanatorium=san, capacity=2, min_nights=1, inventory_count=3
        )
        resp = await client.get(
            "/api/rooms/search?check_in=2026-10-02&check_out=2026-10-05&guests=2"
        )
        assert resp.status_code == 200
        ids = [r["id"] for r in resp.json()]
        assert str(room.id) in ids

    async def test_multi_unit_fits_via_multiple_rooms(
        self, client, db, admin_user
    ):
        # 5 inventory, capacity 2; 3 guests need 2 rooms → still available
        san = await make_sanatorium(
            db, status=SanatoriumStatus.APPROVED, admin_user_id=admin_user.id
        )
        await make_room(db, sanatorium=san, capacity=2, inventory_count=5)
        resp = await client.get(
            f"/api/rooms/search?sanatorium_id={san.id}"
            "&check_in=2026-10-02&check_out=2026-10-05&guests=3"
        )
        rows = resp.json()
        assert len(rows) == 1
        assert rows[0]["available"] is True
        assert rows[0]["rooms_count_needed"] == 2

    async def test_search_returns_unavailable_rows_when_sanatorium_filter(
        self, client, db, admin_user
    ):
        # With sanatorium_id, even unavailable rooms come back with a reason
        san = await make_sanatorium(
            db, status=SanatoriumStatus.APPROVED, admin_user_id=admin_user.id
        )
        room = await make_room(
            db, sanatorium=san, capacity=2, inventory_count=1
        )
        # 5 guests → need 3 rooms, only 1 exists → exceeds_inventory
        resp = await client.get(
            f"/api/rooms/search?sanatorium_id={san.id}"
            "&check_in=2026-10-02&check_out=2026-10-05&guests=5"
        )
        rows = resp.json()
        assert len(rows) == 1
        assert rows[0]["available"] is False
        assert rows[0]["unavailable_reason"] == "exceeds_inventory"
        assert rows[0]["rooms_count_needed"] == 3
        assert str(room.id) == rows[0]["id"]

    async def test_excludes_room_fully_booked(
        self, client, db, admin_user, admin_headers
    ):
        san = await make_sanatorium(
            db, status=SanatoriumStatus.APPROVED, admin_user_id=admin_user.id
        )
        room = await make_room(db, sanatorium=san, inventory_count=1)
        # Block the only unit on Oct 3
        await client.post(
            f"/api/rooms/{room.id}/availability/block",
            json={
                "date_from": "2026-10-03",
                "date_to": "2026-10-04",
                "units_blocked": 1,
            },
            headers=admin_headers,
        )
        resp = await client.get(
            "/api/rooms/search?check_in=2026-10-02&check_out=2026-10-05&guests=2"
        )
        ids = [r["id"] for r in resp.json()]
        assert str(room.id) not in ids

    async def test_excludes_room_with_zero_inventory(
        self, client, db, admin_user
    ):
        san = await make_sanatorium(
            db, status=SanatoriumStatus.APPROVED, admin_user_id=admin_user.id
        )
        room = await make_room(db, sanatorium=san, inventory_count=1)
        # Drop inventory to 0 via direct mutation (simulating "I'm closing this room")
        room.inventory_count = 0
        await db.commit()
        resp = await client.get(
            "/api/rooms/search?check_in=2026-10-02&check_out=2026-10-05&guests=2"
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
