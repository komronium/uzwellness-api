import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.utils import pick_locale
from app.models.news import NewsCategory
from app.schemas.common import Page, Translations


class NewsArticleCreate(BaseModel):
    # Unlike most entities, news content allows missing locales (the frontend
    # falls back). Each field must still carry at least one non-empty locale.
    slug: str | None = Field(default=None, max_length=255)
    title: Translations
    excerpt: Translations
    body: Translations
    category: NewsCategory
    image_url: str | None = Field(default=None, max_length=500)
    is_published: bool = False
    published_at: datetime | None = None

    @model_validator(mode="after")
    def _require_at_least_one_locale(self) -> "NewsArticleCreate":
        for field in ("title", "excerpt", "body"):
            value: Translations = getattr(self, field)
            if not any((value.uz, value.ru, value.en)):
                raise ValueError(f"{field} must include at least one locale")
        return self


class NewsArticleUpdate(BaseModel):
    slug: str | None = Field(default=None, max_length=255)
    title: Translations | None = None
    excerpt: Translations | None = None
    body: Translations | None = None
    category: NewsCategory | None = None
    image_url: str | None = Field(default=None, max_length=500)
    is_published: bool | None = None
    published_at: datetime | None = None


class _NewsReadCommon(BaseModel):
    id: uuid.UUID
    slug: str
    category: NewsCategory
    image_url: str | None
    is_published: bool
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime


class NewsArticleListItem(_NewsReadCommon):
    """Public list item: i18n fields resolved to strings, `body` omitted."""

    title: str
    excerpt: str

    @classmethod
    def from_obj(cls, obj, locale: str) -> "NewsArticleListItem":
        return cls(
            id=obj.id,
            slug=obj.slug,
            category=obj.category,
            image_url=obj.image_url,
            is_published=obj.is_published,
            published_at=obj.published_at,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
            title=pick_locale(obj.title, locale),
            excerpt=pick_locale(obj.excerpt, locale),
        )


class NewsArticleRead(_NewsReadCommon):
    """Public detail: adds the resolved markdown `body`."""

    title: str
    excerpt: str
    body: str

    @classmethod
    def from_obj(cls, obj, locale: str) -> "NewsArticleRead":
        return cls(
            id=obj.id,
            slug=obj.slug,
            category=obj.category,
            image_url=obj.image_url,
            is_published=obj.is_published,
            published_at=obj.published_at,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
            title=pick_locale(obj.title, locale),
            excerpt=pick_locale(obj.excerpt, locale),
            body=pick_locale(obj.body, locale),
        )


class NewsArticleAdminRead(_NewsReadCommon):
    """Admin read: full `{uz,ru,en}` dicts, including drafts."""

    model_config = ConfigDict(from_attributes=True)

    title: dict
    excerpt: dict
    body: dict


class NewsArticleList(Page[NewsArticleListItem]):
    pass


class NewsArticleAdminList(Page[NewsArticleAdminRead]):
    pass
