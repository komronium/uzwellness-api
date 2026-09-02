"""The API must never answer with an unreadable error.

The frontend shows ``detail`` to the guest verbatim, so every failure has to
arrive as JSON with a sentence in it — including the ones nobody wrote code
for.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from httpx import ASGITransport, AsyncClient

from app.api.error_handlers import UnhandledErrorMiddleware, register_error_handlers
from app.main import app as real_app

AMENITY = {
    "code": "duplicate_probe",
    "name": {"uz": "Sauna", "ru": "Сауна", "en": "Sauna"},
    "description": {"uz": "-", "ru": "-", "en": "-"},
    "category": "wellness",
    "scope": "room",
}


def _boom_app() -> FastAPI:
    """A miniature of main.py: same middleware, same registration order."""

    app = FastAPI()
    app.add_middleware(UnhandledErrorMiddleware)
    app.add_middleware(
        CORSMiddleware, allow_origins=["https://uzwellness.com"], allow_methods=["*"]
    )
    register_error_handlers(app)

    @app.get("/boom")
    async def boom() -> dict:
        raise RuntimeError("something nobody handled")

    return app


async def test_unhandled_error_answers_json_with_a_reference(caplog) -> None:
    transport = ASGITransport(app=_boom_app(), raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with caplog.at_level("ERROR", logger="uzwellness.errors"):
            resp = await client.get(
                "/boom", headers={"Origin": "https://uzwellness.com"}
            )

    assert resp.status_code == 500
    assert resp.headers["content-type"].startswith("application/json")
    detail = resp.json()["detail"]
    assert "reference" in detail
    reference = detail.rsplit(" ", 1)[-1]
    # The same reference must be findable in the log next to the traceback.
    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert reference in logged
    assert "RuntimeError" in caplog.text


async def test_unhandled_error_keeps_cors_headers() -> None:
    """Without these the browser reports a CORS failure and hides the body."""

    transport = ASGITransport(app=_boom_app(), raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/boom", headers={"Origin": "https://uzwellness.com"})

    assert resp.headers["access-control-allow-origin"] == "https://uzwellness.com"


def test_error_middleware_sits_inside_cors() -> None:
    """CORS must wrap the error middleware, not the other way round."""

    classes = [m.cls for m in real_app.user_middleware]
    assert CORSMiddleware in classes
    assert UnhandledErrorMiddleware in classes
    assert classes.index(CORSMiddleware) < classes.index(UnhandledErrorMiddleware)


async def test_duplicate_unique_value_is_a_readable_conflict(
    client: AsyncClient, super_admin_headers
) -> None:
    first = await client.post(
        "/api/amenities", json=AMENITY, headers=super_admin_headers
    )
    assert first.status_code == 201, first.text

    second = await client.post(
        "/api/amenities", json=AMENITY, headers=super_admin_headers
    )

    assert second.status_code == 409, second.text
    assert second.json()["detail"] == "This code is already in use"


async def test_session_survives_a_constraint_violation(
    client: AsyncClient, super_admin_headers
) -> None:
    """A rejected write must not poison the next request."""

    await client.post("/api/amenities", json=AMENITY, headers=super_admin_headers)
    await client.post("/api/amenities", json=AMENITY, headers=super_admin_headers)

    resp = await client.post(
        "/api/amenities",
        json={**AMENITY, "code": "duplicate_probe_2"},
        headers=super_admin_headers,
    )
    assert resp.status_code == 201, resp.text
