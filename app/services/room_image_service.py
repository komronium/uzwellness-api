import uuid

from fastapi import Depends
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.ids import uuid7
from app.core.storage import MIME_EXTENSIONS, StorageBackend, url_to_key
from app.models.room import Room, RoomImage


class RoomImageService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, image_id: uuid.UUID) -> RoomImage | None:
        return await self.db.get(RoomImage, image_id)

    async def add(
        self,
        *,
        room: Room,
        content: bytes,
        content_type: str,
        storage: StorageBackend,
        caption: str | None,
        is_primary: bool,
        order: int,
    ) -> RoomImage:
        ext = MIME_EXTENSIONS[content_type]
        image_id = uuid7()
        key = f"rooms/{room.id}/{image_id}.{ext}"
        url = await storage.save(key=key, content=content, content_type=content_type)

        if is_primary:
            await self._unset_primaries(room.id)

        image = RoomImage(
            id=image_id,
            room_id=room.id,
            url=url,
            order=order,
            is_primary=is_primary,
            caption=caption,
        )
        self.db.add(image)
        await self.db.commit()
        await self.db.refresh(image)
        return image

    async def update(
        self,
        image: RoomImage,
        *,
        is_primary: bool | None = None,
        order: int | None = None,
        caption: str | None = None,
    ) -> RoomImage:
        if is_primary is True:
            await self._unset_primaries(image.room_id, except_id=image.id)
            image.is_primary = True
        elif is_primary is False:
            image.is_primary = False
        if order is not None:
            image.order = order
        if caption is not None:
            image.caption = caption
        await self.db.commit()
        await self.db.refresh(image)
        return image

    async def delete(self, image: RoomImage, storage: StorageBackend) -> None:
        await storage.delete(key=url_to_key(image.url))
        await self.db.delete(image)
        await self.db.commit()

    async def _unset_primaries(
        self, room_id: uuid.UUID, *, except_id: uuid.UUID | None = None
    ) -> None:
        stmt = (
            update(RoomImage)
            .where(RoomImage.room_id == room_id)
            .where(RoomImage.is_primary.is_(True))
            .values(is_primary=False)
        )
        if except_id is not None:
            stmt = stmt.where(RoomImage.id != except_id)
        await self.db.execute(stmt)


def get_room_image_service(
    db: AsyncSession = Depends(get_db),
) -> RoomImageService:
    return RoomImageService(db)
