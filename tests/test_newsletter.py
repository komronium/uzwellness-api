from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.newsletter import NewsletterSubscriber


async def test_subscribe_creates_subscriber(
    client: AsyncClient, db: AsyncSession
) -> None:
    resp = await client.post(
        "/api/newsletter/subscribe", json={"email": "reader@example.com"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["email"] == "reader@example.com"
    assert body["subscribed"] is True

    row = await db.scalar(
        select(NewsletterSubscriber).where(
            NewsletterSubscriber.email == "reader@example.com"
        )
    )
    assert row is not None


async def test_subscribe_is_idempotent(client: AsyncClient, db: AsyncSession) -> None:
    for _ in range(2):
        resp = await client.post(
            "/api/newsletter/subscribe", json={"email": "twice@example.com"}
        )
        assert resp.status_code == 200, resp.text

    total = await db.scalar(select(func.count()).select_from(NewsletterSubscriber))
    assert total == 1


async def test_subscribe_normalizes_email_case(
    client: AsyncClient, db: AsyncSession
) -> None:
    resp = await client.post(
        "/api/newsletter/subscribe", json={"email": "Mixed.Case@Example.COM"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["email"] == "mixed.case@example.com"


async def test_subscribe_rejects_invalid_email(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/newsletter/subscribe", json={"email": "not-an-email"}
    )
    assert resp.status_code == 422
