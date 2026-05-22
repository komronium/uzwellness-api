import uuid
from collections.abc import Sequence

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.pagination import paginated
from app.core.utils import merge_translation_fields
from app.models.amenity import Amenity
from app.schemas.amenity import AmenityCreate, AmenityUpdate


class AmenityService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_all(
        self, *, limit: int, offset: int
    ) -> tuple[Sequence[Amenity], int]:
        stmt = select(Amenity).order_by(
            Amenity.category.asc(), Amenity.created_at.asc()
        )
        return await paginated(self.db, stmt, limit=limit, offset=offset)

    async def get_by_id(self, amenity_id: uuid.UUID) -> Amenity | None:
        return await self.db.get(Amenity, amenity_id)

    async def create(self, payload: AmenityCreate) -> Amenity:
        amenity = Amenity(
            name=payload.name.model_dump(),
            description=payload.description.model_dump(),
            category=payload.category,
            icon=payload.icon,
        )
        self.db.add(amenity)
        await self.db.commit()
        await self.db.refresh(amenity)
        return amenity

    async def update(self, amenity: Amenity, payload: AmenityUpdate) -> Amenity:
        data = payload.model_dump(exclude_unset=True)
        merge_translation_fields(amenity, data, ("name", "description"))
        for field, value in data.items():
            setattr(amenity, field, value)
        await self.db.commit()
        await self.db.refresh(amenity)
        return amenity

    async def delete(self, amenity: Amenity) -> None:
        await self.db.delete(amenity)
        await self.db.commit()


def get_amenity_service(db: AsyncSession = Depends(get_db)) -> AmenityService:
    return AmenityService(db)
