"""Request display currency: ?currency= / X-Currency resolution + display_* fields."""

from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.extra_bed import ExtraBedConfig
from tests.factories import make_exchange_rate, make_room, make_sanatorium


@pytest.fixture
async def usd_room(db: AsyncSession):
    """Approved sanatorium with a 100 USD room and USD/RUB rates to UZS."""
    sanatorium = await make_sanatorium(db, slug="fx-test")
    room = await make_room(db, sanatorium=sanatorium, base_price="100.00")
    await make_exchange_rate(db, pair="USD_UZS", rate="12500")
    await make_exchange_rate(db, pair="RUB_UZS", rate="125")
    return room


async def _first_room(
    client: AsyncClient, room, params: dict | None = None, **request_kwargs
) -> dict:
    resp = await client.get(
        "/api/rooms",
        params={"sanatorium_id": str(room.sanatorium_id), **(params or {})},
        **request_kwargs,
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert len(items) == 1
    return items[0]


async def test_default_display_currency_is_uzs(client: AsyncClient, usd_room):
    item = await _first_room(client, usd_room)
    assert item["display_currency"] == "UZS"
    assert Decimal(item["display_price"]) == Decimal("1250000.00")


async def test_query_param_selects_currency(client: AsyncClient, usd_room):
    item = await _first_room(client, usd_room, params={"currency": "RUB"})
    assert item["display_currency"] == "RUB"
    # 100 USD × 12500 / 125 = 10000 RUB
    assert Decimal(item["display_price"]) == Decimal("10000.00")


async def test_header_selects_currency(client: AsyncClient, usd_room):
    item = await _first_room(client, usd_room, headers={"X-Currency": "rub"})
    assert item["display_currency"] == "RUB"
    assert Decimal(item["display_price"]) == Decimal("10000.00")


async def test_query_param_beats_header(client: AsyncClient, usd_room):
    item = await _first_room(
        client, usd_room, params={"currency": "USD"}, headers={"X-Currency": "RUB"}
    )
    assert item["display_currency"] == "USD"
    assert Decimal(item["display_price"]) == Decimal("100.00")


async def test_unsupported_currency_falls_back_to_uzs(client: AsyncClient, usd_room):
    item = await _first_room(client, usd_room, params={"currency": "JPY"})
    assert item["display_currency"] == "UZS"
    assert Decimal(item["display_price"]) == Decimal("1250000.00")


async def test_missing_rate_gives_null_display_price(
    client: AsyncClient, db: AsyncSession
):
    sanatorium = await make_sanatorium(db, slug="fx-norate")
    room = await make_room(db, sanatorium=sanatorium, base_price="100.00")
    # No EUR_UZS rate seeded — currency accepted, price unavailable.
    item = await _first_room(client, room, params={"currency": "EUR"})
    assert item["display_currency"] == "EUR"
    assert item["display_price"] is None


async def test_extra_beds_expose_display_price(client: AsyncClient, db: AsyncSession):
    sanatorium = await make_sanatorium(db, slug="fx-beds")
    config = ExtraBedConfig(
        sanatorium_id=sanatorium.id,
        name={"en": "Child bed"},
        description={"en": "Ages 4-10"},
        price_per_night=Decimal("10.00"),
        currency="USD",
    )
    db.add(config)
    await db.commit()
    await make_exchange_rate(db, pair="USD_UZS", rate="12500")
    await make_exchange_rate(db, pair="RUB_UZS", rate="125")

    resp = await client.get(
        "/api/extra-beds",
        params={"sanatorium_id": str(sanatorium.id), "currency": "RUB"},
    )
    assert resp.status_code == 200, resp.text
    item = resp.json()["items"][0]
    assert item["display_currency"] == "RUB"
    # 10 USD × 12500 / 125 = 1000 RUB
    assert Decimal(item["display_price_per_night"]) == Decimal("1000.00")
