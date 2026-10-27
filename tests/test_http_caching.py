"""Response compression and short public caching for the homepage endpoints."""

import pytest
from httpx import AsyncClient

PUBLIC_CACHE = "public, max-age=300, stale-while-revalidate=600"

PUBLIC_ENDPOINTS = [
    "/api/meta",
    "/api/treatment-focuses/tiles",
    "/api/sanatoriums/featured",
    "/api/admin/homepage-config",
]


@pytest.mark.parametrize("url", PUBLIC_ENDPOINTS)
async def test_shared_public_endpoints_are_briefly_cacheable(
    client: AsyncClient, url: str
) -> None:
    resp = await client.get(url)

    assert resp.status_code == 200, resp.text
    assert resp.headers["cache-control"] == PUBLIC_CACHE
    # The body differs by language and display currency, so a shared cache
    # must key on them or it would serve one guest's language to another.
    vary = {v.strip().lower() for v in resp.headers["vary"].split(",")}
    assert {"accept-language", "x-currency"} <= vary


async def test_per_user_endpoints_are_not_publicly_cached(
    client: AsyncClient, customer_headers
) -> None:
    resp = await client.get("/api/bookings", headers=customer_headers)

    assert resp.status_code == 200, resp.text
    assert "public" not in resp.headers.get("cache-control", "")


async def test_large_json_is_gzipped(client: AsyncClient) -> None:
    resp = await client.get("/api/meta", headers={"Accept-Encoding": "gzip"})

    assert resp.status_code == 200
    assert resp.headers["content-encoding"] == "gzip"
    assert resp.json()  # httpx decodes it transparently


async def test_tiny_responses_are_left_uncompressed(client: AsyncClient) -> None:
    resp = await client.get("/api/health", headers={"Accept-Encoding": "gzip"})

    assert resp.status_code == 200
    assert "content-encoding" not in resp.headers
