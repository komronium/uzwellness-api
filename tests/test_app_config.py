from httpx import AsyncClient

ADMIN_CONFIG_PAYLOAD = {
    "commission": {
        "global_rate": 12.0,
        "overrides": [{"region": "tashkent", "rate": 10.0}],
    },
    "payment_gateways": {"stripe": False, "payme": True, "click": True},
    "email_templates": {
        "booking_confirmed": {
            "subject": "Booking {{code}} confirmed",
            "body": "Hello {{guest_name}}!",
        },
        "booking_cancelled": {"subject": "Cancelled", "body": "Sorry {{guest_name}}."},
    },
    "feature_flags": {
        "maintenance_mode": True,
        "new_registrations": False,
        "b2b_portal": True,
        "flight_module": False,
        "train_module": True,
        "reviews_enabled": True,
    },
}

HOMEPAGE_CONFIG_PAYLOAD = {
    "hero_slides": [
        {
            "id": "0",
            "video": "https://cdn.test/hero.mp4",
            "poster": "https://cdn.test/hero.jpg",
            "enabled": True,
        }
    ],
    "trust_stats": {
        "sanatoriums": "250+",
        "countries": "50",
        "rating": "4.9",
        "savings": "Up to 70%",
    },
    "section_visibility": {
        "trust_bar": True,
        "why_uzbekistan": False,
        "destinations": True,
        "treatments": True,
        "featured_sanatoriums": True,
        "packages": False,
        "how_it_works": True,
        "testimonials": True,
        "b2b": True,
    },
}


async def test_get_admin_config_returns_defaults(
    client: AsyncClient, super_admin_headers
) -> None:
    resp = await client.get("/api/admin/config", headers=super_admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["commission"]["global_rate"] == 0.0
    assert body["payment_gateways"] == {"stripe": True, "payme": True, "click": True}
    assert body["feature_flags"]["maintenance_mode"] is False


async def test_put_then_get_admin_config_round_trips(
    client: AsyncClient, super_admin_headers
) -> None:
    put = await client.put(
        "/api/admin/config",
        headers=super_admin_headers,
        json=ADMIN_CONFIG_PAYLOAD,
    )
    assert put.status_code == 200, put.text

    get = await client.get("/api/admin/config", headers=super_admin_headers)
    assert get.status_code == 200
    assert get.json() == ADMIN_CONFIG_PAYLOAD


async def test_admin_config_requires_super_admin(
    client: AsyncClient, admin_headers, customer_headers
) -> None:
    for headers in (admin_headers, customer_headers):
        assert (
            await client.get("/api/admin/config", headers=headers)
        ).status_code == 403
        assert (
            await client.put(
                "/api/admin/config", headers=headers, json=ADMIN_CONFIG_PAYLOAD
            )
        ).status_code == 403


async def test_admin_config_rejects_out_of_range_commission(
    client: AsyncClient, super_admin_headers
) -> None:
    payload = {"commission": {"global_rate": 150.0, "overrides": []}}
    resp = await client.put(
        "/api/admin/config", headers=super_admin_headers, json=payload
    )
    assert resp.status_code == 422


async def test_homepage_config_get_is_public_with_defaults(
    client: AsyncClient,
) -> None:
    resp = await client.get("/api/admin/homepage-config")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["hero_slides"] == []
    assert body["trust_stats"]["sanatoriums"] == "200+"
    assert body["section_visibility"]["trust_bar"] is True


async def test_put_then_get_homepage_config_round_trips(
    client: AsyncClient, super_admin_headers
) -> None:
    put = await client.put(
        "/api/admin/homepage-config",
        headers=super_admin_headers,
        json=HOMEPAGE_CONFIG_PAYLOAD,
    )
    assert put.status_code == 200, put.text

    get = await client.get("/api/admin/homepage-config")
    assert get.status_code == 200
    assert get.json() == HOMEPAGE_CONFIG_PAYLOAD


async def test_homepage_config_put_requires_super_admin(
    client: AsyncClient, admin_headers
) -> None:
    resp = await client.put(
        "/api/admin/homepage-config",
        headers=admin_headers,
        json=HOMEPAGE_CONFIG_PAYLOAD,
    )
    assert resp.status_code == 403


async def test_put_overwrites_previous_config(
    client: AsyncClient, super_admin_headers
) -> None:
    await client.put(
        "/api/admin/homepage-config",
        headers=super_admin_headers,
        json=HOMEPAGE_CONFIG_PAYLOAD,
    )
    updated = {**HOMEPAGE_CONFIG_PAYLOAD, "hero_slides": []}
    await client.put(
        "/api/admin/homepage-config", headers=super_admin_headers, json=updated
    )

    resp = await client.get("/api/admin/homepage-config")
    assert resp.json()["hero_slides"] == []
