import uuid
from collections.abc import Sequence

from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.amenity import Amenity
from app.schemas.amenity import AmenityCreate, AmenityUpdate


class AmenityService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_all(
        self, *, limit: int, offset: int
    ) -> tuple[Sequence[Amenity], int]:
        base = select(Amenity)
        total = (
            await self.db.execute(select(func.count()).select_from(base.subquery()))
        ).scalar_one()
        stmt = (
            base.order_by(Amenity.category.asc(), Amenity.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        return rows, total

    async def get_by_id(self, amenity_id: uuid.UUID) -> Amenity | None:
        stmt = select(Amenity).where(Amenity.id == amenity_id)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def create(self, payload: AmenityCreate) -> Amenity:
        amenity = Amenity(
            name=payload.name.model_dump(exclude_none=True),
            category=payload.category,
            icon=payload.icon,
        )
        self.db.add(amenity)
        await self.db.commit()
        await self.db.refresh(amenity)
        return amenity

    async def update(self, amenity: Amenity, payload: AmenityUpdate) -> Amenity:
        data = payload.model_dump(exclude_unset=True)
        if "name" in data and data["name"] is not None:
            data["name"] = {k: v for k, v in data["name"].items() if v is not None}
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
