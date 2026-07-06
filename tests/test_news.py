import uuid

from httpx import AsyncClient

from tests.factories import make_png

PNG = make_png()


def _payload(**overrides) -> dict:
    base = {
        "title": {
            "uz": "Eng yaxshi sanatoriylar",
            "ru": "Лучшие санатории",
            "en": "Best sanatoriums",
        },
        "excerpt": {
            "uz": "Qisqacha.",
            "ru": "Кратко.",
            "en": "In short.",
        },
        "body": {
            "uz": "## Sarlavha\n\nMatn.",
            "ru": "## Заголовок\n\nТекст.",
            "en": "## Heading\n\nBody text.",
        },
        "category": "guide",
    }
    base.update(overrides)
    return base


# ── create / permissions ─────────────────────────────────────────────────────


async def test_super_admin_creates_article(
    client: AsyncClient, super_admin_headers
) -> None:
    resp = await client.post("/api/news", json=_payload(), headers=super_admin_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["title"]["en"] == "Best sanatoriums"
    assert body["slug"] == "best-sanatoriums"
    assert body["category"] == "guide"
    assert body["is_published"] is False
    assert body["published_at"] is None
    assert body["image_url"] is None


async def test_sanatorium_admin_cannot_create(
    client: AsyncClient, admin_headers
) -> None:
    resp = await client.post("/api/news", json=_payload(), headers=admin_headers)
    assert resp.status_code == 403


async def test_customer_cannot_create(client: AsyncClient, customer_headers) -> None:
    resp = await client.post("/api/news", json=_payload(), headers=customer_headers)
    assert resp.status_code == 403


async def test_anonymous_cannot_create(client: AsyncClient) -> None:
    resp = await client.post("/api/news", json=_payload())
    assert resp.status_code in (401, 403)


async def test_create_requires_at_least_one_locale(
    client: AsyncClient, super_admin_headers
) -> None:
    resp = await client.post(
        "/api/news",
        json=_payload(title={}),
        headers=super_admin_headers,
    )
    assert resp.status_code == 422


async def test_create_allows_partial_locales(
    client: AsyncClient, super_admin_headers
) -> None:
    resp = await client.post(
        "/api/news",
        json=_payload(title={"en": "English only"}, slug="english-only"),
        headers=super_admin_headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["title"] == {"en": "English only"}


async def test_explicit_slug_is_normalized(
    client: AsyncClient, super_admin_headers
) -> None:
    resp = await client.post(
        "/api/news",
        json=_payload(slug="My New Article!"),
        headers=super_admin_headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["slug"] == "my-new-article"


async def test_duplicate_slug_on_create_conflicts(
    client: AsyncClient, super_admin_headers
) -> None:
    await client.post(
        "/api/news", json=_payload(slug="dup"), headers=super_admin_headers
    )
    resp = await client.post(
        "/api/news",
        json=_payload(slug="dup", title={"en": "Other"}),
        headers=super_admin_headers,
    )
    assert resp.status_code == 409


# ── public list ──────────────────────────────────────────────────────────────


async def _create(client, headers, **overrides) -> dict:
    resp = await client.post("/api/news", json=_payload(**overrides), headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_public_list_shows_only_published(
    client: AsyncClient, super_admin_headers
) -> None:
    await _create(
        client,
        super_admin_headers,
        slug="live",
        is_published=True,
        published_at="2026-02-01T00:00:00Z",
    )
    await _create(client, super_admin_headers, slug="draft")  # unpublished

    resp = await client.get("/api/news")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["slug"] == "live"


async def test_public_list_newest_first(
    client: AsyncClient, super_admin_headers
) -> None:
    await _create(
        client,
        super_admin_headers,
        slug="older",
        title={"en": "Older"},
        is_published=True,
        published_at="2026-01-01T00:00:00Z",
    )
    await _create(
        client,
        super_admin_headers,
        slug="newer",
        title={"en": "Newer"},
        is_published=True,
        published_at="2026-06-01T00:00:00Z",
    )
    resp = await client.get("/api/news")
    slugs = [i["slug"] for i in resp.json()["items"]]
    assert slugs == ["newer", "older"]


async def test_public_list_omits_body(client: AsyncClient, super_admin_headers) -> None:
    await _create(
        client,
        super_admin_headers,
        slug="live",
        is_published=True,
        published_at="2026-02-01T00:00:00Z",
    )
    resp = await client.get("/api/news?lang=ru")
    item = resp.json()["items"][0]
    assert item["title"] == "Лучшие санатории"
    assert "body" not in item
    assert isinstance(item["excerpt"], str)


async def test_public_list_category_filter(
    client: AsyncClient, super_admin_headers
) -> None:
    await _create(
        client,
        super_admin_headers,
        slug="a-guide",
        category="guide",
        is_published=True,
        published_at="2026-02-01T00:00:00Z",
    )
    await _create(
        client,
        super_admin_headers,
        slug="a-health",
        category="health",
        title={"en": "Health"},
        is_published=True,
        published_at="2026-02-01T00:00:00Z",
    )
    resp = await client.get("/api/news?category=health")
    slugs = [i["slug"] for i in resp.json()["items"]]
    assert slugs == ["a-health"]


async def test_include_drafts_only_for_super_admin(
    client: AsyncClient, super_admin_headers, customer_headers
) -> None:
    await _create(client, super_admin_headers, slug="draft")  # unpublished

    # super_admin sees the draft
    resp = await client.get(
        "/api/news?include_drafts=true", headers=super_admin_headers
    )
    assert resp.json()["total"] == 1

    # a customer passing the flag is ignored
    resp = await client.get("/api/news?include_drafts=true", headers=customer_headers)
    assert resp.json()["total"] == 0


async def test_include_translations_returns_dicts(
    client: AsyncClient, super_admin_headers
) -> None:
    await _create(
        client,
        super_admin_headers,
        slug="live",
        is_published=True,
        published_at="2026-02-01T00:00:00Z",
    )
    resp = await client.get(
        "/api/news?include_translations=true", headers=super_admin_headers
    )
    item = resp.json()["items"][0]
    assert item["title"] == {
        "uz": "Eng yaxshi sanatoriylar",
        "ru": "Лучшие санатории",
        "en": "Best sanatoriums",
    }


# ── public detail ────────────────────────────────────────────────────────────


async def test_public_detail_by_slug(client: AsyncClient, super_admin_headers) -> None:
    await _create(
        client,
        super_admin_headers,
        slug="live",
        is_published=True,
        published_at="2026-02-01T00:00:00Z",
    )
    resp = await client.get("/api/news/live?lang=en")
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "Best sanatoriums"
    assert body["body"] == "## Heading\n\nBody text."


async def test_public_detail_draft_is_404(
    client: AsyncClient, super_admin_headers
) -> None:
    await _create(client, super_admin_headers, slug="draft")
    resp = await client.get("/api/news/draft")
    assert resp.status_code == 404


async def test_super_admin_can_view_draft_detail(
    client: AsyncClient, super_admin_headers
) -> None:
    created = await _create(client, super_admin_headers, slug="draft")
    resp = await client.get(
        f"/api/news/{created['id']}?include_translations=true",
        headers=super_admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["is_published"] is False


async def test_public_detail_unknown_is_404(client: AsyncClient) -> None:
    resp = await client.get(f"/api/news/{uuid.uuid4()}")
    assert resp.status_code == 404
    resp = await client.get("/api/news/no-such-slug")
    assert resp.status_code == 404


# ── update ───────────────────────────────────────────────────────────────────


async def test_patch_merges_translations(
    client: AsyncClient, super_admin_headers
) -> None:
    created = await _create(client, super_admin_headers, slug="live")
    resp = await client.patch(
        f"/api/news/{created['id']}",
        json={"title": {"uz": "Yangi sarlavha"}},
        headers=super_admin_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["title"]["uz"] == "Yangi sarlavha"
    assert body["title"]["en"] == "Best sanatoriums"


async def test_publish_stamps_published_at(
    client: AsyncClient, super_admin_headers
) -> None:
    created = await _create(client, super_admin_headers, slug="live")
    assert created["published_at"] is None
    resp = await client.patch(
        f"/api/news/{created['id']}",
        json={"is_published": True},
        headers=super_admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["published_at"] is not None


async def test_slug_unchanged_on_title_edit(
    client: AsyncClient, super_admin_headers
) -> None:
    created = await _create(client, super_admin_headers, slug="stable-url")
    resp = await client.patch(
        f"/api/news/{created['id']}",
        json={"title": {"en": "Totally different headline"}},
        headers=super_admin_headers,
    )
    assert resp.json()["slug"] == "stable-url"


async def test_slug_change_allowed(client: AsyncClient, super_admin_headers) -> None:
    created = await _create(client, super_admin_headers, slug="old-url")
    resp = await client.patch(
        f"/api/news/{created['id']}",
        json={"slug": "new-url"},
        headers=super_admin_headers,
    )
    assert resp.json()["slug"] == "new-url"


async def test_duplicate_slug_on_update_conflicts(
    client: AsyncClient, super_admin_headers
) -> None:
    await _create(client, super_admin_headers, slug="taken")
    other = await _create(
        client, super_admin_headers, slug="mine", title={"en": "Mine"}
    )
    resp = await client.patch(
        f"/api/news/{other['id']}",
        json={"slug": "taken"},
        headers=super_admin_headers,
    )
    assert resp.status_code == 409


async def test_customer_cannot_update(
    client: AsyncClient, super_admin_headers, customer_headers
) -> None:
    created = await _create(client, super_admin_headers, slug="live")
    resp = await client.patch(
        f"/api/news/{created['id']}",
        json={"title": {"en": "hacked"}},
        headers=customer_headers,
    )
    assert resp.status_code == 403


# ── delete ───────────────────────────────────────────────────────────────────


async def test_super_admin_deletes_article(
    client: AsyncClient, super_admin_headers
) -> None:
    created = await _create(client, super_admin_headers, slug="live")
    resp = await client.delete(
        f"/api/news/{created['id']}", headers=super_admin_headers
    )
    assert resp.status_code == 204
    assert (await client.get(f"/api/news/{created['id']}")).status_code == 404


async def test_sanatorium_admin_cannot_delete(
    client: AsyncClient, super_admin_headers, admin_headers
) -> None:
    created = await _create(client, super_admin_headers, slug="live")
    resp = await client.delete(f"/api/news/{created['id']}", headers=admin_headers)
    assert resp.status_code == 403


# ── cover image ──────────────────────────────────────────────────────────────


async def test_upload_and_delete_cover_image(
    client: AsyncClient, super_admin_headers, storage
) -> None:
    created = await _create(client, super_admin_headers, slug="live")
    upload = await client.post(
        f"/api/news/{created['id']}/cover-image",
        headers=super_admin_headers,
        files={"file": ("cover.png", PNG, "image/png")},
    )
    assert upload.status_code == 200, upload.text
    url = upload.json()["image_url"]
    assert url.endswith(".webp")
    key = url.removeprefix(storage.url_prefix + "/")
    assert storage.objects[key][8:12] == b"WEBP"

    remove = await client.delete(
        f"/api/news/{created['id']}/cover-image", headers=super_admin_headers
    )
    assert remove.status_code == 200
    assert remove.json()["image_url"] is None
    assert key not in storage.objects
