"""Tests for PATCH /rooms/{id}/availability/{date} and RoomRead extra fields."""
from __future__ import annotations

from datetime import date, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.availability import RoomAvailability
from app.models.sanatorium import SanatoriumStatus
from tests.factories import make_room, make_sanatorium


class TestAvailabilityUpsert:
    async def test_upsert_creates_when_missing(
        self,
        client: AsyncClient,
        db: AsyncSession,
        admin_user,
        admin_headers,
    ):
        san = await make_sanatorium(
            db, slug="upsert-1", admin_user_id=admin_user.id,
            status=SanatoriumStatus.APPROVED,
        )
        room = await make_room(db, sanatorium=san, inventory_count=5)
        target = (date.today() + timedelta(days=7)).isoformat()
        resp = await client.patch(
            f"/api/rooms/{room.id}/availability/{target}",
            json={"units_blocked": 2},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["inventory_count"] == 5
        assert body["units_blocked"] == 2
        assert body["units_booked"] == 0
        assert body["units_available"] == 3

    async def test_upsert_updates_existing_preserves_booked(
        self,
        client: AsyncClient,
        db: AsyncSession,
        admin_user,
        admin_headers,
    ):
        san = await make_sanatorium(
            db, slug="upsert-2", admin_user_id=admin_user.id,
            status=SanatoriumStatus.APPROVED,
        )
        room = await make_room(db, sanatorium=san, inventory_count=10)
        target = date.today() + timedelta(days=7)

        # Existing row: 2 already booked, 0 blocked
        row = RoomAvailability(
            room_id=room.id, date=target, units_blocked=0, units_booked=2
        )
        db.add(row)
        await db.commit()

        # Block 3 → preserves booked
        resp = await client.patch(
            f"/api/rooms/{room.id}/availability/{target.isoformat()}",
            json={"units_blocked": 3},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json() == {
            "date": target.isoformat(),
            "inventory_count": 10,
            "units_blocked": 3,
            "units_booked": 2,
            "units_available": 5,
        }

    async def test_upsert_blocked_plus_booked_exceeds_inventory_409(
        self,
        client: AsyncClient,
        db: AsyncSession,
        admin_user,
        admin_headers,
    ):
        san = await make_sanatorium(
            db, slug="upsert-3", admin_user_id=admin_user.id,
            status=SanatoriumStatus.APPROVED,
        )
        room = await make_room(db, sanatorium=san, inventory_count=5)
        target = date.today() + timedelta(days=7)
        row = RoomAvailability(
            room_id=room.id, date=target, units_blocked=0, units_booked=3
        )
        db.add(row)
        await db.commit()
        # 3 booked, try blocking 3 more → 6 > inventory 5 → 409
        resp = await client.patch(
            f"/api/rooms/{room.id}/availability/{target.isoformat()}",
            json={"units_blocked": 3},
            headers=admin_headers,
        )
        assert resp.status_code == 409

    async def test_upsert_block_full_inventory(
        self,
        client: AsyncClient,
        db: AsyncSession,
        admin_user,
        admin_headers,
    ):
        san = await make_sanatorium(
            db, slug="upsert-4", admin_user_id=admin_user.id,
            status=SanatoriumStatus.APPROVED,
        )
        room = await make_room(db, sanatorium=san, inventory_count=5)
        target = (date.today() + timedelta(days=7)).isoformat()
        resp = await client.patch(
            f"/api/rooms/{room.id}/availability/{target}",
            json={"units_blocked": 5},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["units_blocked"] == 5
        assert resp.json()["units_available"] == 0

    async def test_upsert_anon_returns_401(
        self, client: AsyncClient, db: AsyncSession
    ):
        san = await make_sanatorium(db, slug="upsert-anon")
        room = await make_room(db, sanatorium=san)
        target = (date.today() + timedelta(days=7)).isoformat()
        resp = await client.patch(
            f"/api/rooms/{room.id}/availability/{target}",
            json={"units_blocked": 1},
        )
        assert resp.status_code == 401

    async def test_upsert_other_admin_returns_403(
        self,
        client: AsyncClient,
        db: AsyncSession,
        admin_user,
        admin_headers,
    ):
        # Create sanatorium owned by someone else
        san = await make_sanatorium(db, slug="upsert-other")
        room = await make_room(db, sanatorium=san)
        target = (date.today() + timedelta(days=7)).isoformat()
        resp = await client.patch(
            f"/api/rooms/{room.id}/availability/{target}",
            json={"units_blocked": 1},
            headers=admin_headers,
        )
        assert resp.status_code == 403


class TestRoomAvailabilityFields:
    async def test_room_with_inventory_has_availability(
        self, client: AsyncClient, db: AsyncSession
    ):
        san = await make_sanatorium(db, slug="avail-1")
        room = await make_room(db, sanatorium=san, inventory_count=3)
        resp = await client.get(f"/api/rooms/{room.id}")
        body = resp.json()
        assert body["inventory_count"] == 3
        assert body["has_availability"] is True

    async def test_room_with_zero_inventory_no_availability(
        self, client: AsyncClient, db: AsyncSession
    ):
        san = await make_sanatorium(db, slug="avail-2")
        room = await make_room(db, sanatorium=san, inventory_count=1)
        room.inventory_count = 0
        await db.commit()
        resp = await client.get(f"/api/rooms/{room.id}")
        body = resp.json()
        assert body["inventory_count"] == 0
        assert body["has_availability"] is False

    async def test_inactive_room_no_availability(
        self, client: AsyncClient, db: AsyncSession
    ):
        san = await make_sanatorium(db, slug="avail-3")
        room = await make_room(db, sanatorium=san, inventory_count=5, is_active=False)
        resp = await client.get(f"/api/rooms/{room.id}")
        body = resp.json()
        assert body["has_availability"] is False
