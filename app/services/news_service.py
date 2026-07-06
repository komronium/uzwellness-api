import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from fastapi import Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.ids import uuid7
from app.core.pagination import paginated
from app.core.slug import slugify
from app.core.storage import MIME_EXTENSIONS, StorageBackend, url_to_key
from app.core.utils import merge_translation_fields, pick_locale
from app.models.news import NewsArticle, NewsCategory
from app.schemas.news import NewsArticleCreate, NewsArticleUpdate


class NewsService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, article_id: uuid.UUID) -> NewsArticle | None:
        return await self.db.get(NewsArticle, article_id)

    async def get_by_slug(self, slug: str) -> NewsArticle | None:
        return await self.db.scalar(select(NewsArticle).where(NewsArticle.slug == slug))

    async def list_articles(
        self,
        *,
        limit: int,
        offset: int,
        published_only: bool = True,
        category: NewsCategory | None = None,
    ) -> tuple[Sequence[NewsArticle], int]:
        stmt = select(NewsArticle)
        if published_only:
            stmt = stmt.where(NewsArticle.is_published.is_(True))
        if category is not None:
            stmt = stmt.where(NewsArticle.category == category)
        # Newest first; drafts (no published_at) fall back to created_at.
        stmt = stmt.order_by(
            func.coalesce(NewsArticle.published_at, NewsArticle.created_at).desc()
        )
        return await paginated(self.db, stmt, limit=limit, offset=offset)

    async def create(self, payload: NewsArticleCreate) -> NewsArticle:
        title_dict = payload.title.model_dump(exclude_none=True)
        slug = await self._resolve_slug(payload.slug, title_dict=title_dict)

        published_at = payload.published_at
        if payload.is_published and published_at is None:
            published_at = datetime.now(UTC)

        article = NewsArticle(
            slug=slug,
            title=title_dict,
            excerpt=payload.excerpt.model_dump(exclude_none=True),
            body=payload.body.model_dump(exclude_none=True),
            category=payload.category,
            image_url=payload.image_url,
            is_published=payload.is_published,
            published_at=published_at,
        )
        self.db.add(article)
        await self.db.commit()
        await self.db.refresh(article)
        return article

    async def update(
        self, article: NewsArticle, payload: NewsArticleUpdate
    ) -> NewsArticle:
        data = payload.model_dump(exclude_unset=True)
        merge_translation_fields(article, data, ("title", "excerpt", "body"))

        # Slug is the canonical SEO URL: only change it when explicitly given,
        # never silently on a title edit. Duplicates are rejected (409).
        if data.get("slug"):
            article.slug = await self._resolve_slug(
                data["slug"], title_dict=article.title, exclude_id=article.id
            )
        data.pop("slug", None)

        # First publish stamps published_at unless the caller set it explicitly.
        if (
            data.get("is_published") is True
            and article.published_at is None
            and "published_at" not in data
        ):
            data["published_at"] = datetime.now(UTC)

        for field, value in data.items():
            setattr(article, field, value)
        await self.db.commit()
        await self.db.refresh(article)
        return article

    async def delete(self, article: NewsArticle) -> None:
        await self.db.delete(article)
        await self.db.commit()

    async def update_cover_image(
        self,
        article: NewsArticle,
        *,
        content: bytes,
        content_type: str,
        storage: StorageBackend,
    ) -> NewsArticle:
        await self._delete_local_cover(article, storage)
        ext = MIME_EXTENSIONS[content_type]
        image_id = uuid7()
        key = f"news/{article.id}/{image_id}.{ext}"
        article.image_url = await storage.save(
            key=key, content=content, content_type=content_type
        )
        await self.db.commit()
        await self.db.refresh(article)
        return article

    async def delete_cover_image(
        self, article: NewsArticle, storage: StorageBackend
    ) -> NewsArticle:
        await self._delete_local_cover(article, storage)
        article.image_url = None
        await self.db.commit()
        await self.db.refresh(article)
        return article

    async def _resolve_slug(
        self,
        raw: str | None,
        *,
        title_dict: dict,
        exclude_id: uuid.UUID | None = None,
    ) -> str:
        seed = raw or pick_locale(title_dict, "en")
        slug = slugify(seed, fallback="article")
        existing = await self.db.scalar(
            select(NewsArticle).where(NewsArticle.slug == slug)
        )
        if existing is not None and existing.id != exclude_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"News article with slug '{slug}' already exists",
            )
        return slug

    @staticmethod
    async def _delete_local_cover(
        article: NewsArticle, storage: StorageBackend
    ) -> None:
        url = article.image_url
        prefix = settings.UPLOAD_URL_PREFIX.rstrip("/") + "/"
        if url and url.startswith(prefix):
            await storage.delete(key=url_to_key(url))


def get_news_service(db: AsyncSession = Depends(get_db)) -> NewsService:
    return NewsService(db)
