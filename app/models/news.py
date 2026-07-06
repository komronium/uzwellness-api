from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, String, Uuid
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.ids import uuid7
from app.models.base import TimestampMixin


class NewsCategory(StrEnum):
    GUIDE = "guide"
    HEALTH = "health"
    PLATFORM = "platform"
    DESTINATIONS = "destinations"


class NewsArticle(TimestampMixin, Base):
    """A multilingual news/blog article that drives public SEO pages.

    `title`, `excerpt` and `body` are `{uz,ru,en}` JSONB dicts (body is
    markdown per locale). `slug` is the stable, admin-controlled public URL —
    it is never auto-suffixed, and duplicates are rejected on write.
    Drafts (`is_published=False`) are hidden from public endpoints.
    """

    __tablename__ = "news_articles"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    slug: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    title: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    excerpt: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    body: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    category: Mapped[NewsCategory] = mapped_column(
        SQLEnum(
            NewsCategory,
            native_enum=False,
            length=20,
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
        index=True,
    )
    image_url: Mapped[str | None] = mapped_column(String(500))

    is_published: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false", index=True
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
