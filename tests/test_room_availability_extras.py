"""Tests for PATCH /rooms/{id}/availability/{date} and RoomRead extra fields."""

from __future__ import annotations

import json
from datetime import date, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.availability import RoomAvailability
from app.models.sanatorium import SanatoriumStatus
from tests.factories import InMemoryStorage, make_png, make_room, make_sanatorium

PNG = make_png()


def _multipart(content: bytes, **fields: str | bool | int):
    files = {"file": ("room.png", content, "image/png")}
    data = {k: str(v) for k, v in fields.items()}
    return files, data


class TestAvailabilityUpsert:
    async def test_upsert_creates_when_missing(
        self,
        client: AsyncClient,
        db: AsyncSession,
        admin_user,
        admin_headers,
    ):
        san = await make_sanatorium(
            db,
            slug="upsert-1",
            admin_user_id=admin_user.id,
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
            db,
            slug="upsert-2",
            admin_user_id=admin_user.id,
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
            db,
            slug="upsert-3",
            admin_user_id=admin_user.id,
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
            db,
            slug="upsert-4",
            admin_user_id=admin_user.id,
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

    async def test_upsert_anon_returns_401(self, client: AsyncClient, db: AsyncSession):
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


class TestRoomImageMetadata:
    async def test_upload_room_image_with_metadata(
        self,
        client: AsyncClient,
        db: AsyncSession,
        admin_user,
        admin_headers,
        storage: InMemoryStorage,
    ):
        san = await make_sanatorium(
            db,
            slug="room-image-meta",
            admin_user_id=admin_user.id,
            status=SanatoriumStatus.APPROVED,
        )
        room = await make_room(db, sanatorium=san)
        files, data = _multipart(
            PNG,
            caption="Classic room",
            is_primary=True,
            is_video=True,
            is_360=True,
            category="bathroom",
            caption_i18n=json.dumps({"uz": "Hammom", "en": "Bathroom"}),
            alt_text=json.dumps({"en": "Private bathroom"}),
            tags=json.dumps(["bathroom", "shower"]),
            order=2,
        )
        resp = await client.post(
            f"/api/rooms/{room.id}/images",
            files=files,
            data=data,
            headers=admin_headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["caption"] == "Classic room"
        assert body["is_primary"] is True
        assert body["is_video"] is True
        assert body["is_360"] is True
        assert body["category"] == "bathroom"
        assert body["caption_i18n"]["uz"] == "Hammom"
        assert body["alt_text"]["en"] == "Private bathroom"
        assert body["tags"] == ["bathroom", "shower"]
        key = body["url"].removeprefix(storage.url_prefix + "/")
        assert key in storage.objects

    async def test_patch_room_image_metadata(
        self, client: AsyncClient, db: AsyncSession, admin_user, admin_headers
    ):
        san = await make_sanatorium(
            db,
            slug="room-image-patch-meta",
            admin_user_id=admin_user.id,
            status=SanatoriumStatus.APPROVED,
        )
        room = await make_room(db, sanatorium=san)
        files, data = _multipart(PNG)
        created = await client.post(
            f"/api/rooms/{room.id}/images",
            files=files,
            data=data,
            headers=admin_headers,
        )
        assert created.status_code == 201, created.text

        resp = await client.patch(
            f"/api/rooms/{room.id}/images/{created.json()['id']}",
            json={
                "is_video": True,
                "is_360": True,
                "category": "room",
                "caption_i18n": {"en": "Junior suite"},
                "alt_text": {"en": "Junior suite bed"},
                "tags": ["bed", "suite"],
            },
            headers=admin_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["is_video"] is True
        assert body["is_360"] is True
        assert body["category"] == "room"
        assert body["caption_i18n"]["en"] == "Junior suite"
        assert body["alt_text"]["en"] == "Junior suite bed"
        assert body["tags"] == ["bed", "suite"]
