from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.newsletter import NewsletterSubscriber


class NewsletterService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def subscribe(self, email: str) -> NewsletterSubscriber:
        email = email.lower()
        existing = await self.db.scalar(
            select(NewsletterSubscriber).where(NewsletterSubscriber.email == email)
        )
        if existing is not None:
            return existing
        subscriber = NewsletterSubscriber(email=email)
        self.db.add(subscriber)
        try:
            await self.db.commit()
        except IntegrityError:
            # Concurrent subscribe with the same email; the unique index won.
            await self.db.rollback()
            existing = await self.db.scalar(
                select(NewsletterSubscriber).where(NewsletterSubscriber.email == email)
            )
            if existing is not None:
                return existing
            raise
        await self.db.refresh(subscriber)
        return subscriber


def get_newsletter_service(db: AsyncSession = Depends(get_db)) -> NewsletterService:
    return NewsletterService(db)
