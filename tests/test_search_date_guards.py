"""Every public search rejects a check-in in the past.

Searching a past date used to return bookable offers that then failed at
checkout with "Check-in cannot be in the past" — the guest saw prices for a
stay they could never book.
"""

from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.utils import today_tashkent
from app.models.sanatorium import SanatoriumStatus
from tests.factories import make_room, make_sanatorium

PAST_DETAIL = "Check-in cannot be in the past. Please pick today or a later date."


def _stay(start_offset: int) -> tuple[str, str]:
    check_in = today_tashkent() + timedelta(days=start_offset)
    return check_in.isoformat(), (check_in + timedelta(days=2)).isoformat()


@pytest.fixture
async def sanatorium(db: AsyncSession, admin_user):
    sanatorium = await make_sanatorium(
        db, status=SanatoriumStatus.APPROVED, admin_user_id=admin_user.id
    )
    await make_room(db, sanatorium=sanatorium, base_price="100.00", capacity=2)
    return sanatorium


async def _stay_search(client: AsyncClient, sanatorium, check_in, check_out):
    return await client.get(
        "/api/sanatoriums/search",
        params={"check_in": check_in, "check_out": check_out},
    )


async def _room_search(client: AsyncClient, sanatorium, check_in, check_out):
    return await client.get(
        "/api/rooms/search",
        params={
            "check_in": check_in,
            "check_out": check_out,
            "sanatorium_id": str(sanatorium.id),
        },
    )


async def _offer_search(client: AsyncClient, sanatorium, check_in, check_out):
    return await client.post(
        f"/api/sanatoriums/{sanatorium.id}/room-offers/search",
        json={
            "check_in": check_in,
            "check_out": check_out,
            "rooms": [{"adults": 2, "children": []}],
        },
    )


SEARCHES = [_stay_search, _room_search, _offer_search]


@pytest.mark.parametrize("search", SEARCHES)
async def test_search_rejects_past_check_in(
    client: AsyncClient, sanatorium, search
) -> None:
    resp = await search(client, sanatorium, *_stay(-1))

    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"] == PAST_DETAIL


@pytest.mark.parametrize("search", SEARCHES)
async def test_search_accepts_today(client: AsyncClient, sanatorium, search) -> None:
    resp = await search(client, sanatorium, *_stay(0))

    assert resp.status_code == 200, resp.text


# --- an upper bound on the stay itself ---------------------------------------
#
# Inventory rows are created on first booking and a pending booking holds them
# until it is paid or cancelled, so an unbounded stay let one unpaid booking
# take every room of a type for years — and made searches price every night.


def _long_stay(nights: int, start_offset: int = 1) -> tuple[str, str]:
    check_in = today_tashkent() + timedelta(days=start_offset)
    return check_in.isoformat(), (check_in + timedelta(days=nights)).isoformat()


@pytest.mark.parametrize("search", SEARCHES)
async def test_search_rejects_a_stay_longer_than_the_cap(
    client: AsyncClient, sanatorium, search
) -> None:
    resp = await search(client, sanatorium, *_long_stay(settings.MAX_STAY_NIGHTS + 1))

    assert resp.status_code in (400, 422), resp.text
    assert str(settings.MAX_STAY_NIGHTS) in resp.text


@pytest.mark.parametrize("search", SEARCHES)
async def test_search_rejects_a_check_in_beyond_the_horizon(
    client: AsyncClient, sanatorium, search
) -> None:
    resp = await search(
        client,
        sanatorium,
        *_long_stay(2, start_offset=settings.BOOKING_HORIZON_DAYS + 1),
    )

    assert resp.status_code in (400, 422), resp.text


async def test_booking_rejects_a_stay_longer_than_the_cap(
    client: AsyncClient, db: AsyncSession, sanatorium, customer_headers
) -> None:
    room = await make_room(db, sanatorium=sanatorium, name="Long", capacity=2)
    check_in, check_out = _long_stay(settings.MAX_STAY_NIGHTS + 1)

    resp = await client.post(
        "/api/bookings",
        headers=customer_headers,
        json={"room_id": str(room.id), "check_in": check_in, "check_out": check_out},
    )

    assert resp.status_code == 400, resp.text
    assert f"{settings.MAX_STAY_NIGHTS} nights" in resp.json()["detail"]


async def test_booking_at_the_cap_is_accepted(
    client: AsyncClient, db: AsyncSession, sanatorium, customer_headers
) -> None:
    room = await make_room(db, sanatorium=sanatorium, name="AtCap", capacity=2)
    check_in, check_out = _long_stay(settings.MAX_STAY_NIGHTS)

    resp = await client.post(
        "/api/bookings",
        headers=customer_headers,
        json={"room_id": str(room.id), "check_in": check_in, "check_out": check_out},
    )

    assert resp.status_code == 201, resp.text


async def test_public_availability_refuses_an_unbounded_range(
    client: AsyncClient, db: AsyncSession, sanatorium
) -> None:
    """Anonymous, and it used to build one row per day: 0001→9999 is 3.6M."""

    room = await make_room(db, sanatorium=sanatorium, name="Range")

    resp = await client.get(
        f"/api/rooms/{room.id}/availability",
        params={"from": "2026-01-01", "to": "9999-12-31"},
    )

    assert resp.status_code == 400, resp.text
    assert str(settings.MAX_DATE_RANGE_DAYS) in resp.json()["detail"]


async def test_admin_calendar_refuses_an_unbounded_range(
    client: AsyncClient, admin_headers, sanatorium
) -> None:
    resp = await client.get(
        "/api/availability/calendar",
        headers=admin_headers,
        params={
            "sanatorium_id": str(sanatorium.id),
            "from": "2026-01-01",
            "to": "2099-12-31",
        },
    )

    assert resp.status_code == 400, resp.text


async def test_offer_search_refuses_an_impossible_party(
    client: AsyncClient, sanatorium
) -> None:
    """Pricing walks every guest; a million adults kept a worker for minutes."""

    check_in, check_out = _stay(1)

    resp = await client.post(
        f"/api/sanatoriums/{sanatorium.id}/room-offers/search",
        json={
            "check_in": check_in,
            "check_out": check_out,
            "rooms": [{"adults": 1_000_000, "children": []}],
        },
    )

    assert resp.status_code == 422, resp.text


async def test_offer_search_at_the_largest_party_stays_fast(
    client: AsyncClient, sanatorium
) -> None:
    import time

    check_in, check_out = _stay(1)
    room = {"adults": 20, "children": [{"age": 5}] * 10}
    started = time.monotonic()

    resp = await client.post(
        f"/api/sanatoriums/{sanatorium.id}/room-offers/search",
        json={"check_in": check_in, "check_out": check_out, "rooms": [room] * 8},
    )

    assert resp.status_code == 200, resp.text
    assert time.monotonic() - started < 5
