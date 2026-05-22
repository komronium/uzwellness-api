"""Integration tests for SUPER_ADMIN_ONLY_FIELDS on Sanatorium update."""
from __future__ import annotations

from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import make_sanatorium


class TestSuperAdminOnlyFields:
    async def test_super_admin_can_set_platform_commission(
        self, client: AsyncClient, db: AsyncSession, super_admin_headers
    ):
        s = await make_sanatorium(db, slug="comm-sa")
        resp = await client.patch(
            f"/api/sanatoriums/{s.id}",
            json={"platform_commission_percent": "12.5"},
            headers=super_admin_headers,
        )
        assert resp.status_code == 200
        assert Decimal(resp.json()["platform_commission_percent"]) == Decimal("12.5")

    async def test_super_admin_can_set_b2b_commission(
        self, client: AsyncClient, db: AsyncSession, super_admin_headers
    ):
        s = await make_sanatorium(db, slug="comm-sa-2")
        resp = await client.patch(
            f"/api/sanatoriums/{s.id}",
            json={"b2b_commission_percent": "7"},
            headers=super_admin_headers,
        )
        assert resp.status_code == 200
        assert Decimal(resp.json()["b2b_commission_percent"]) == Decimal("7")

    async def test_super_admin_can_set_agent_discount_tiers(
        self, client: AsyncClient, db: AsyncSession, super_admin_headers
    ):
        s = await make_sanatorium(db, slug="tiers-sa")
        resp = await client.patch(
            f"/api/sanatoriums/{s.id}",
            json={
                "agent_discount_tiers": [
                    {"min_bookings": 5, "discount_percent": "5"},
                    {"min_bookings": 10, "discount_percent": "10"},
                ]
            },
            headers=super_admin_headers,
        )
        assert resp.status_code == 200
        tiers = resp.json()["agent_discount_tiers"]
        assert len(tiers) == 2
        assert tiers[0]["min_bookings"] == 5

    async def test_admin_cannot_set_platform_commission(
        self, client: AsyncClient, db: AsyncSession, admin_user, admin_headers
    ):
        s = await make_sanatorium(db, slug="comm-adm", admin_user_id=admin_user.id)
        resp = await client.patch(
            f"/api/sanatoriums/{s.id}",
            json={"platform_commission_percent": "50"},
            headers=admin_headers,
        )
        assert resp.status_code == 403
        assert "super_admin" in resp.json()["detail"]

    async def test_admin_cannot_set_b2b_commission(
        self, client: AsyncClient, db: AsyncSession, admin_user, admin_headers
    ):
        s = await make_sanatorium(db, slug="comm-adm-2", admin_user_id=admin_user.id)
        resp = await client.patch(
            f"/api/sanatoriums/{s.id}",
            json={"b2b_commission_percent": "1"},
            headers=admin_headers,
        )
        assert resp.status_code == 403

    async def test_admin_cannot_set_agent_tiers(
        self, client: AsyncClient, db: AsyncSession, admin_user, admin_headers
    ):
        s = await make_sanatorium(db, slug="tiers-adm", admin_user_id=admin_user.id)
        resp = await client.patch(
            f"/api/sanatoriums/{s.id}",
            json={"agent_discount_tiers": []},
            headers=admin_headers,
        )
        assert resp.status_code == 403

    async def test_admin_cannot_set_destination_id(
        self, client: AsyncClient, db: AsyncSession, admin_user, admin_headers
    ):
        # Pinning a sanatorium to a homepage marketing tile is super_admin-only.
        s = await make_sanatorium(db, slug="dest-adm", admin_user_id=admin_user.id)
        resp = await client.patch(
            f"/api/sanatoriums/{s.id}",
            json={"destination_id": "00000000-0000-0000-0000-000000000000"},
            headers=admin_headers,
        )
        assert resp.status_code == 403
        assert "super_admin" in resp.json()["detail"]

    async def test_admin_can_still_edit_normal_fields(
        self, client: AsyncClient, db: AsyncSession, admin_user, admin_headers
    ):
        s = await make_sanatorium(db, slug="norm", admin_user_id=admin_user.id)
        resp = await client.patch(
            f"/api/sanatoriums/{s.id}",
            json={"name": {"uz": "Renamed"}, "city": "Samarqand"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["name"]["uz"] == "Renamed"
        assert resp.json()["city"] == "Samarqand"
