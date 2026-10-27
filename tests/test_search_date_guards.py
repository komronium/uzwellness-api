"""Every public search rejects a check-in in the past.

Searching a past date used to return bookable offers that then failed at
checkout with "Check-in cannot be in the past" — the guest saw prices for a
stay they could never book.
"""

from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

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
