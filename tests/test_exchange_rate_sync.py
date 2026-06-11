from datetime import UTC, datetime
from decimal import Decimal

import pytest
from httpx import AsyncClient

from app.schemas.exchange_rate import ExchangeRateUpsert
from app.services.exchange_rate_sync import parse_cbu_rates

CBU_SAMPLE = [
    {"Ccy": "USD", "Rate": "12054.03", "Nominal": "1", "Date": "11.06.2026"},
    {"Ccy": "EUR", "Rate": "13932.05", "Nominal": "1", "Date": "11.06.2026"},
    {"Ccy": "RUB", "Rate": "167.05", "Nominal": "1", "Date": "11.06.2026"},
    {"Ccy": "KZT", "Rate": "223.17", "Nominal": "10", "Date": "11.06.2026"},
    {"Ccy": "JPY", "Rate": "813.32", "Nominal": "10", "Date": "11.06.2026"},
]


def test_parse_cbu_rates_filters_and_normalizes_nominal():
    parsed = {p.pair: p for p in parse_cbu_rates(CBU_SAMPLE)}

    assert set(parsed) == {"USD_UZS", "EUR_UZS", "RUB_UZS", "KZT_UZS"}
    assert parsed["USD_UZS"].rate == Decimal("12054.030000")
    # Nominal=10 means the rate covers 10 units
    assert parsed["KZT_UZS"].rate == Decimal("22.317000")
    assert parsed["USD_UZS"].valid_from == datetime(2026, 6, 11, tzinfo=UTC)


def test_parse_cbu_rates_skips_unconfigured_currencies():
    parsed = parse_cbu_rates(
        [{"Ccy": "JPY", "Rate": "813.32", "Nominal": "10", "Date": "11.06.2026"}]
    )
    assert parsed == []


@pytest.fixture
def fake_cbu(monkeypatch):
    async def _fetch() -> list[ExchangeRateUpsert]:
        return parse_cbu_rates(CBU_SAMPLE)

    monkeypatch.setattr("app.api.routers.exchange_rates.fetch_cbu_rates", _fetch)


async def test_sync_endpoint_upserts_rates(
    client: AsyncClient, super_admin_headers: dict[str, str], fake_cbu
):
    resp = await client.post("/api/exchange-rates/sync", headers=super_admin_headers)
    assert resp.status_code == 200, resp.text
    pairs = {item["pair"]: item for item in resp.json()}
    assert set(pairs) == {"USD_UZS", "EUR_UZS", "RUB_UZS", "KZT_UZS"}
    assert Decimal(pairs["USD_UZS"]["rate"]) == Decimal("12054.030000")

    # Re-sync updates in place — no duplicate pairs
    resp = await client.post("/api/exchange-rates/sync", headers=super_admin_headers)
    assert resp.status_code == 200

    resp = await client.get("/api/exchange-rates")
    assert resp.status_code == 200
    assert len(resp.json()) == 4


async def test_sync_endpoint_requires_super_admin(
    client: AsyncClient, customer_headers: dict[str, str], fake_cbu
):
    resp = await client.post("/api/exchange-rates/sync", headers=customer_headers)
    assert resp.status_code == 403

    resp = await client.post("/api/exchange-rates/sync")
    assert resp.status_code == 401


async def test_manual_override_survives_sync(
    client: AsyncClient, super_admin_headers: dict[str, str], fake_cbu
):
    resp = await client.patch(
        "/api/exchange-rates",
        headers=super_admin_headers,
        json={
            "pair": "USD_UZS",
            "rate": "13000",
            "valid_from": "2026-06-11T00:00:00Z",
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["source"] == "manual"

    resp = await client.post("/api/exchange-rates/sync", headers=super_admin_headers)
    assert resp.status_code == 200

    rates = {r["pair"]: r for r in (await client.get("/api/exchange-rates")).json()}
    # The manual override is untouched; other pairs come from CBU.
    assert Decimal(rates["USD_UZS"]["rate"]) == Decimal("13000")
    assert rates["USD_UZS"]["source"] == "manual"
    assert rates["EUR_UZS"]["source"] == "cbu"


async def test_delete_rate_returns_pair_to_auto_sync(
    client: AsyncClient, super_admin_headers: dict[str, str], fake_cbu
):
    resp = await client.patch(
        "/api/exchange-rates",
        headers=super_admin_headers,
        json={
            "pair": "USD_UZS",
            "rate": "13000",
            "valid_from": "2026-06-11T00:00:00Z",
        },
    )
    assert resp.status_code == 200

    resp = await client.delete(
        "/api/exchange-rates/USD_UZS", headers=super_admin_headers
    )
    assert resp.status_code == 204

    resp = await client.post("/api/exchange-rates/sync", headers=super_admin_headers)
    assert resp.status_code == 200

    rates = {r["pair"]: r for r in (await client.get("/api/exchange-rates")).json()}
    assert Decimal(rates["USD_UZS"]["rate"]) == Decimal("12054.030000")
    assert rates["USD_UZS"]["source"] == "cbu"


async def test_delete_missing_rate_404(
    client: AsyncClient, super_admin_headers: dict[str, str]
):
    resp = await client.delete(
        "/api/exchange-rates/USD_UZS", headers=super_admin_headers
    )
    assert resp.status_code == 404


async def test_currencies_endpoint_lists_selector_options(
    client: AsyncClient, super_admin_headers: dict[str, str], fake_cbu
):
    await client.post("/api/exchange-rates/sync", headers=super_admin_headers)

    resp = await client.get("/api/exchange-rates/currencies")
    assert resp.status_code == 200
    body = resp.json()
    assert body["default_currency"] == "UZS"
    by_code = {c["currency"]: c for c in body["currencies"]}
    assert set(by_code) == {"UZS", "USD", "EUR", "RUB", "KZT"}
    assert Decimal(by_code["UZS"]["rate_to_uzs"]) == Decimal("1")
    assert by_code["USD"]["is_available"] is True
    assert Decimal(by_code["USD"]["rate_to_uzs"]) == Decimal("12054.030000")
