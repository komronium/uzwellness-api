import uuid

from fastapi import APIRouter, Depends, File, Query, UploadFile, status

from app.api.deps import (
    IncludeTranslationsDep,
    LocaleDep,
    OptionalUser,
    is_super_admin,
    not_found,
    require_roles,
)
from app.core.pagination import Pagination
from app.core.storage import StorageBackend, get_storage
from app.core.uploads import read_image_upload_as_webp
from app.models.news import NewsCategory
from app.models.user import UserRole
from app.schemas.news import (
    NewsArticleAdminList,
    NewsArticleAdminRead,
    NewsArticleCreate,
    NewsArticleList,
    NewsArticleListItem,
    NewsArticleRead,
    NewsArticleUpdate,
)
from app.services.news_service import NewsService, get_news_service

router = APIRouter(prefix="/news", tags=["News"])

require_super_admin = require_roles(UserRole.SUPER_ADMIN)


@router.get("", response_model=NewsArticleList | NewsArticleAdminList)
async def list_news(
    current_user: OptionalUser,
    locale: LocaleDep,
    include_translations: IncludeTranslationsDep,
    page: Pagination,
    category: NewsCategory | None = Query(default=None),
    include_drafts: bool = Query(
        default=False, description="Include unpublished drafts (super_admin only)"
    ),
    news: NewsService = Depends(get_news_service),
) -> NewsArticleList | NewsArticleAdminList:
    super_admin = is_super_admin(current_user)
    show_drafts = include_drafts and super_admin
    items, total = await news.list_articles(
        limit=page.limit,
        offset=page.offset,
        published_only=not show_drafts,
        category=category,
    )
    if include_translations and super_admin:
        return NewsArticleAdminList(
            items=[NewsArticleAdminRead.model_validate(a) for a in items],
            total=total,
            limit=page.limit,
            offset=page.offset,
        )
    return NewsArticleList(
        items=[NewsArticleListItem.from_obj(a, locale) for a in items],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get(
    "/{article_id_or_slug}", response_model=NewsArticleRead | NewsArticleAdminRead
)
async def get_news_article(
    article_id_or_slug: str,
    current_user: OptionalUser,
    locale: LocaleDep,
    include_translations: IncludeTranslationsDep,
    news: NewsService = Depends(get_news_service),
) -> NewsArticleRead | NewsArticleAdminRead:
    article = None
    try:
        article_uuid = uuid.UUID(article_id_or_slug)
    except ValueError:
        article_uuid = None
    if article_uuid is not None:
        article = await news.get_by_id(article_uuid)
    if article is None:
        article = await news.get_by_slug(article_id_or_slug)
    if article is None:
        raise not_found("News article not found")
    super_admin = is_super_admin(current_user)
    if not article.is_published and not super_admin:
        raise not_found("News article not found")
    if include_translations and super_admin:
        return NewsArticleAdminRead.model_validate(article)
    return NewsArticleRead.from_obj(article, locale)


@router.post(
    "",
    response_model=NewsArticleAdminRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_super_admin)],
)
async def create_news_article(
    payload: NewsArticleCreate,
    news: NewsService = Depends(get_news_service),
) -> NewsArticleAdminRead:
    return NewsArticleAdminRead.model_validate(await news.create(payload))


@router.patch(
    "/{article_id}",
    response_model=NewsArticleAdminRead,
    dependencies=[Depends(require_super_admin)],
)
async def update_news_article(
    article_id: uuid.UUID,
    payload: NewsArticleUpdate,
    news: NewsService = Depends(get_news_service),
) -> NewsArticleAdminRead:
    article = await news.get_by_id(article_id)
    if article is None:
        raise not_found("News article not found")
    return NewsArticleAdminRead.model_validate(await news.update(article, payload))


@router.post(
    "/{article_id}/cover-image",
    response_model=NewsArticleAdminRead,
    dependencies=[Depends(require_super_admin)],
)
async def upload_news_cover_image(
    article_id: uuid.UUID,
    file: UploadFile = File(...),
    news: NewsService = Depends(get_news_service),
    storage: StorageBackend = Depends(get_storage),
) -> NewsArticleAdminRead:
    article = await news.get_by_id(article_id)
    if article is None:
        raise not_found("News article not found")
    content, mime = await read_image_upload_as_webp(file)
    updated = await news.update_cover_image(
        article, content=content, content_type=mime, storage=storage
    )
    return NewsArticleAdminRead.model_validate(updated)


@router.delete(
    "/{article_id}/cover-image",
    response_model=NewsArticleAdminRead,
    dependencies=[Depends(require_super_admin)],
)
async def delete_news_cover_image(
    article_id: uuid.UUID,
    news: NewsService = Depends(get_news_service),
    storage: StorageBackend = Depends(get_storage),
) -> NewsArticleAdminRead:
    article = await news.get_by_id(article_id)
    if article is None:
        raise not_found("News article not found")
    updated = await news.delete_cover_image(article, storage)
    return NewsArticleAdminRead.model_validate(updated)


@router.delete(
    "/{article_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_super_admin)],
)
async def delete_news_article(
    article_id: uuid.UUID,
    news: NewsService = Depends(get_news_service),
) -> None:
    article = await news.get_by_id(article_id)
    if article is None:
        raise not_found("News article not found")
    await news.delete(article)
