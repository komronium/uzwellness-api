import json
import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.user import UserRole
from tests.factories import (
    InMemoryStorage,
    make_png,
    make_sanatorium,
    make_user,
)

PNG = make_png()


def _multipart(content: bytes, **fields: str | bool | int):
    files = {"file": ("dot.png", content, "image/png")}
    data = {k: str(v) for k, v in fields.items()}
    return files, data


async def test_upload_as_super_admin(
    client: AsyncClient,
    db: AsyncSession,
    super_admin_headers,
    storage: InMemoryStorage,
) -> None:
    sanatorium = await make_sanatorium(db, slug="upload-target")
    files, data = _multipart(
        PNG,
        caption="hi",
        is_primary=True,
        is_360=True,
        category="treatment",
        caption_i18n=json.dumps({"uz": "Muolaja xonasi", "en": "Treatment room"}),
        alt_text=json.dumps({"en": "Treatment bath room"}),
        tags=json.dumps(["medical", "bath"]),
        order=1,
    )
    resp = await client.post(
        f"/api/sanatoriums/{sanatorium.id}/images",
        headers=super_admin_headers,
        files=files,
        data=data,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["caption"] == "hi"
    assert body["is_primary"] is True
    assert body["is_360"] is True
    assert body["category"] == "treatment"
    assert body["caption_i18n"]["uz"] == "Muolaja xonasi"
    assert body["alt_text"]["en"] == "Treatment bath room"
    assert body["tags"] == ["medical", "bath"]
    assert body["url"].endswith(".png")
    # actually saved into the in-memory storage
    key = body["url"].removeprefix(storage.url_prefix + "/")
    assert key in storage.objects
    assert storage.objects[key] == PNG


async def test_upload_as_owning_admin(
    client: AsyncClient, db: AsyncSession, admin_user, admin_headers
) -> None:
    sanatorium = await make_sanatorium(db, slug="mine", admin_user_id=admin_user.id)
    files, data = _multipart(PNG)
    resp = await client.post(
        f"/api/sanatoriums/{sanatorium.id}/images",
        headers=admin_headers,
        files=files,
        data=data,
    )
    assert resp.status_code == 201


async def test_upload_as_other_admin_returns_403(
    client: AsyncClient, db: AsyncSession, admin_headers
) -> None:
    other_admin = await make_user(db, email="o-admin-img@test.com", role=UserRole.ADMIN)
    sanatorium = await make_sanatorium(
        db, slug="not-mine", admin_user_id=other_admin.id
    )
    files, data = _multipart(PNG)
    resp = await client.post(
        f"/api/sanatoriums/{sanatorium.id}/images",
        headers=admin_headers,
        files=files,
        data=data,
    )
    assert resp.status_code == 403


async def test_upload_as_customer_returns_403(
    client: AsyncClient, db: AsyncSession, customer_headers
) -> None:
    sanatorium = await make_sanatorium(db, slug="cust-blocked")
    files, data = _multipart(PNG)
    resp = await client.post(
        f"/api/sanatoriums/{sanatorium.id}/images",
        headers=customer_headers,
        files=files,
        data=data,
    )
    assert resp.status_code == 403


async def test_upload_anonymous_returns_401(
    client: AsyncClient, db: AsyncSession
) -> None:
    sanatorium = await make_sanatorium(db, slug="anon-blocked")
    files, data = _multipart(PNG)
    resp = await client.post(
        f"/api/sanatoriums/{sanatorium.id}/images",
        files=files,
        data=data,
    )
    assert resp.status_code == 401


async def test_upload_invalid_mime_returns_415(
    client: AsyncClient, db: AsyncSession, super_admin_headers
) -> None:
    sanatorium = await make_sanatorium(db, slug="mime-check")
    files = {"file": ("not-image.png", b"not an image", "image/png")}
    resp = await client.post(
        f"/api/sanatoriums/{sanatorium.id}/images",
        headers=super_admin_headers,
        files=files,
    )
    assert resp.status_code == 415


async def test_upload_empty_returns_400(
    client: AsyncClient, db: AsyncSession, super_admin_headers
) -> None:
    sanatorium = await make_sanatorium(db, slug="empty-check")
    files = {"file": ("empty.png", b"", "image/png")}
    resp = await client.post(
        f"/api/sanatoriums/{sanatorium.id}/images",
        headers=super_admin_headers,
        files=files,
    )
    assert resp.status_code == 400


async def test_upload_too_large_returns_413(
    client: AsyncClient, db: AsyncSession, super_admin_headers
) -> None:
    sanatorium = await make_sanatorium(db, slug="size-check")
    oversized = b"\x89PNG\r\n\x1a\n" + b"A" * (
        settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    )
    files = {"file": ("big.png", oversized, "image/png")}
    resp = await client.post(
        f"/api/sanatoriums/{sanatorium.id}/images",
        headers=super_admin_headers,
        files=files,
    )
    assert resp.status_code == 413


async def test_upload_to_nonexistent_returns_404(
    client: AsyncClient, super_admin_headers
) -> None:
    files, data = _multipart(PNG)
    resp = await client.post(
        f"/api/sanatoriums/{uuid.uuid4()}/images",
        headers=super_admin_headers,
        files=files,
        data=data,
    )
    assert resp.status_code == 404


async def test_upload_primary_toggles_previous(
    client: AsyncClient, db: AsyncSession, super_admin_headers
) -> None:
    sanatorium = await make_sanatorium(db, slug="toggle")

    files1, data1 = _multipart(PNG, is_primary=True, order=1)
    resp1 = await client.post(
        f"/api/sanatoriums/{sanatorium.id}/images",
        headers=super_admin_headers,
        files=files1,
        data=data1,
    )
    assert resp1.status_code == 201
    first_id = resp1.json()["id"]

    files2, data2 = _multipart(PNG, is_primary=True, order=2)
    resp2 = await client.post(
        f"/api/sanatoriums/{sanatorium.id}/images",
        headers=super_admin_headers,
        files=files2,
        data=data2,
    )
    assert resp2.status_code == 201

    detail = await client.get(f"/api/sanatoriums/{sanatorium.id}")
    images = {img["id"]: img for img in detail.json()["images"]}
    assert images[first_id]["is_primary"] is False
    assert images[resp2.json()["id"]]["is_primary"] is True


async def test_update_image_metadata(
    client: AsyncClient, db: AsyncSession, super_admin_headers
) -> None:
    sanatorium = await make_sanatorium(db, slug="metadata-update")
    files, data = _multipart(PNG, caption="old")
    created = await client.post(
        f"/api/sanatoriums/{sanatorium.id}/images",
        headers=super_admin_headers,
        files=files,
        data=data,
    )
    assert created.status_code == 201, created.text

    resp = await client.patch(
        f"/api/sanatoriums/{sanatorium.id}/images/{created.json()['id']}",
        json={
            "is_360": True,
            "category": "restaurant",
            "caption": "new",
            "caption_i18n": {"uz": "Restoran", "ru": "Ресторан"},
            "alt_text": {"en": "Restaurant buffet"},
            "tags": ["food", "buffet"],
        },
        headers=super_admin_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["caption"] == "new"
    assert body["is_360"] is True
    assert body["category"] == "restaurant"
    assert body["caption_i18n"]["uz"] == "Restoran"
    assert body["alt_text"]["en"] == "Restaurant buffet"
    assert body["tags"] == ["food", "buffet"]
