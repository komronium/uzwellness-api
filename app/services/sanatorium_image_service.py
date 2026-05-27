import uuid

from fastapi import Depends
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.ids import uuid7
from app.core.storage import MIME_EXTENSIONS, StorageBackend, url_to_key
from app.models.sanatorium import Sanatorium, SanatoriumImage


class SanatoriumImageService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, image_id: uuid.UUID) -> SanatoriumImage | None:
        return await self.db.get(SanatoriumImage, image_id)

    async def add(
        self,
        *,
        sanatorium: Sanatorium,
        content: bytes,
        content_type: str,
        storage: StorageBackend,
        caption: str | None,
        is_primary: bool,
        is_360: bool,
        category: str | None,
        caption_i18n: dict | None,
        alt_text: dict | None,
        tags: list[str] | None,
        order: int,
    ) -> SanatoriumImage:
        ext = MIME_EXTENSIONS[content_type]
        image_id = uuid7()
        key = f"sanatoriums/{sanatorium.id}/{image_id}.{ext}"
        url = await storage.save(key=key, content=content, content_type=content_type)

        if is_primary:
            await self._unset_primaries(sanatorium.id)

        image = SanatoriumImage(
            id=image_id,
            sanatorium_id=sanatorium.id,
            url=url,
            order=order,
            is_primary=is_primary,
            is_360=is_360,
            category=category,
            caption=caption,
            caption_i18n=caption_i18n or {},
            alt_text=alt_text or {},
            tags=tags or [],
        )
        self.db.add(image)
        await self.db.commit()
        await self.db.refresh(image)
        return image

    async def update(
        self,
        image: SanatoriumImage,
        *,
        is_primary: bool | None = None,
        is_360: bool | None = None,
        category: str | None = None,
        order: int | None = None,
        caption: str | None = None,
        caption_i18n: dict | None = None,
        alt_text: dict | None = None,
        tags: list[str] | None = None,
    ) -> SanatoriumImage:
        if is_primary is True:
            await self._unset_primaries(image.sanatorium_id, except_id=image.id)
            image.is_primary = True
        elif is_primary is False:
            image.is_primary = False
        if is_360 is not None:
            image.is_360 = is_360
        if category is not None:
            image.category = category
        if order is not None:
            image.order = order
        if caption is not None:
            image.caption = caption
        if caption_i18n is not None:
            image.caption_i18n = caption_i18n
        if alt_text is not None:
            image.alt_text = alt_text
        if tags is not None:
            image.tags = tags
        await self.db.commit()
        await self.db.refresh(image)
        return image

    async def delete(self, image: SanatoriumImage, storage: StorageBackend) -> None:
        await storage.delete(key=url_to_key(image.url))
        await self.db.delete(image)
        await self.db.commit()

    async def _unset_primaries(
        self, sanatorium_id: uuid.UUID, *, except_id: uuid.UUID | None = None
    ) -> None:
        stmt = (
            update(SanatoriumImage)
            .where(SanatoriumImage.sanatorium_id == sanatorium_id)
            .where(SanatoriumImage.is_primary.is_(True))
            .values(is_primary=False)
        )
        if except_id is not None:
            stmt = stmt.where(SanatoriumImage.id != except_id)
        await self.db.execute(stmt)


def get_sanatorium_image_service(
    db: AsyncSession = Depends(get_db),
) -> SanatoriumImageService:
    return SanatoriumImageService(db)
