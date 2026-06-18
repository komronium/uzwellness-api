"""Booking confirmation voucher (PDF) endpoint."""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sanatorium import SanatoriumStatus
from tests.factories import make_room, make_sanatorium

_CHECK_IN = "2027-05-10"
_CHECK_OUT = "2027-05-13"  # 3 nights


async def _book(client: AsyncClient, db: AsyncSession, admin_user, customer_headers):
    san = await make_sanatorium(
        db, status=SanatoriumStatus.APPROVED, admin_user_id=admin_user.id
    )
    room = await make_room(
        db, sanatorium=san, capacity=2, min_nights=1, inventory_count=3
    )
    resp = await client.post(
        "/api/bookings",
        json={
            "room_id": str(room.id),
            "check_in": _CHECK_IN,
            "check_out": _CHECK_OUT,
            "guests": 2,
        },
        headers=customer_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_voucher_returns_pdf(
    client: AsyncClient, db: AsyncSession, admin_user, customer_headers
) -> None:
    booking = await _book(client, db, admin_user, customer_headers)

    resp = await client.get(
        f"/api/bookings/{booking['id']}/voucher.pdf?lang=ru",
        headers=customer_headers,
    )

    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:5] == b"%PDF-"
    assert "attachment" in resp.headers["content-disposition"]
    assert booking["reservation_number"] in resp.headers["content-disposition"]


async def test_voucher_locales_render(
    client: AsyncClient, db: AsyncSession, admin_user, customer_headers
) -> None:
    booking = await _book(client, db, admin_user, customer_headers)
    for lang in ("uz", "ru", "en"):
        resp = await client.get(
            f"/api/bookings/{booking['id']}/voucher.pdf?lang={lang}",
            headers=customer_headers,
        )
        assert resp.status_code == 200, (lang, resp.text)
        assert resp.content[:5] == b"%PDF-"


async def test_voucher_requires_visibility(
    client: AsyncClient, db: AsyncSession, admin_user, customer_headers
) -> None:
    booking = await _book(client, db, admin_user, customer_headers)
    # An unauthenticated request cannot download someone else's voucher.
    resp = await client.get(f"/api/bookings/{booking['id']}/voucher.pdf")
    assert resp.status_code == 401
