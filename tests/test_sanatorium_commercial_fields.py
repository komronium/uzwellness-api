"""Commercial terms on a property are not public.

The platform commission, B2B commission and the owning admin's user id used to
ship in every public sanatorium response, so any visitor (or a competing
property) could read the platform's margin per property.
"""

from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sanatorium import SanatoriumStatus
from app.models.user import UserRole
from tests.conftest import _login
from tests.factories import make_sanatorium, make_user

SECRET_FIELDS = ("platform_commission_percent", "b2b_commission_percent")
TIERS = [{"min_bookings": 1, "discount_percent": "5.00"}]


@pytest.fixture
async def sanatorium(db: AsyncSession, admin_user):
    sanatorium = await make_sanatorium(
        db, status=SanatoriumStatus.APPROVED, admin_user_id=admin_user.id
    )
    sanatorium.platform_commission_percent = Decimal("20")
    sanatorium.b2b_commission_percent = Decimal("10")
    sanatorium.agent_discount_tiers = TIERS
    await db.commit()
    return sanatorium


def _reads(sanatorium):
    """Every public read path that returns this property."""
    return [
        ("get", f"/api/sanatoriums/{sanatorium.id}", {}),
        ("get", f"/api/sanatoriums/{sanatorium.id}", {"include_translations": "true"}),
        ("get", f"/api/sanatoriums/slug/{sanatorium.slug}", {}),
        ("list", "/api/sanatoriums", {}),
        ("list", "/api/sanatoriums", {"include_translations": "true"}),
    ]


async def _fetch_all(client: AsyncClient, sanatorium, headers=None) -> list[dict]:
    bodies = []
    for kind, url, params in _reads(sanatorium):
        resp = await client.get(url, params=params, headers=headers or {})
        assert resp.status_code == 200, (url, params, resp.text)
        body = resp.json()
        if kind == "list":
            body = next(i for i in body["items"] if i["id"] == str(sanatorium.id))
        bodies.append(body)
    return bodies


async def test_anonymous_visitor_sees_no_commercial_terms(
    client: AsyncClient, sanatorium
) -> None:
    for body in await _fetch_all(client, sanatorium):
        for field in SECRET_FIELDS:
            assert body[field] is None, field
        assert body["admin_user_id"] is None
        assert body["agent_discount_tiers"] == []


async def test_customer_sees_no_commercial_terms(
    client: AsyncClient, sanatorium, customer_headers
) -> None:
    for body in await _fetch_all(client, sanatorium, customer_headers):
        for field in SECRET_FIELDS:
            assert body[field] is None, field
        assert body["admin_user_id"] is None


async def test_other_property_admin_sees_no_commercial_terms(
    client: AsyncClient, db: AsyncSession, sanatorium
) -> None:
    await make_user(db, email="other-admin@test.com", role=UserRole.ADMIN)
    headers = await _login(client, "other-admin@test.com", "passw0rd")

    body = (
        await client.get(f"/api/sanatoriums/{sanatorium.id}", headers=headers)
    ).json()

    assert body["platform_commission_percent"] is None
    assert body["admin_user_id"] is None


async def test_agent_sees_discount_tiers_but_not_commissions(
    client: AsyncClient, db: AsyncSession, sanatorium
) -> None:
    await make_user(db, email="agent@test.com", role=UserRole.AGENT)
    headers = await _login(client, "agent@test.com", "passw0rd")

    for body in await _fetch_all(client, sanatorium, headers):
        assert body["agent_discount_tiers"] == TIERS
        for field in SECRET_FIELDS:
            assert body[field] is None, field


async def test_owning_admin_sees_commercial_terms(
    client: AsyncClient, sanatorium, admin_user, admin_headers
) -> None:
    for body in await _fetch_all(client, sanatorium, admin_headers):
        assert body["platform_commission_percent"] == "20.00"
        assert body["b2b_commission_percent"] == "10.00"
        assert body["admin_user_id"] == str(admin_user.id)
        assert body["agent_discount_tiers"] == TIERS


async def test_super_admin_sees_commercial_terms(
    client: AsyncClient, sanatorium, super_admin_headers
) -> None:
    for body in await _fetch_all(client, sanatorium, super_admin_headers):
        assert body["platform_commission_percent"] == "20.00"
        assert body["admin_user_id"] is not None
