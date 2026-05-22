import uuid
from collections.abc import Sequence

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.pagination import paginated
from app.core.slug import slugify as _slugify
from app.core.utils import merge_translation_fields, pick_locale
from app.models.region import Region
from app.schemas.region import RegionCreate, RegionUpdate


def slugify(text: str) -> str:
    return _slugify(text, fallback="region")


class RegionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_all(
        self,
        *,
        limit: int,
        offset: int,
        active_only: bool = False,
    ) -> tuple[Sequence[Region], int]:
        stmt = select(Region).order_by(Region.created_at.asc())
        if active_only:
            stmt = stmt.where(Region.is_active.is_(True))
        return await paginated(self.db, stmt, limit=limit, offset=offset)

    async def get_by_id(self, region_id: uuid.UUID) -> Region | None:
        return await self.db.get(Region, region_id)

    async def get_by_slug(self, slug: str) -> Region | None:
        return await self.db.scalar(
            select(Region).where(Region.slug == slug)
        )

    async def _resolve_slug(
        self, base: str, exclude_id: uuid.UUID | None = None
    ) -> str:
        candidate = base
        suffix = 2
        while True:
            existing = await self.db.scalar(
                select(Region).where(Region.slug == candidate)
            )
            if existing is None or existing.id == exclude_id:
                return candidate
            candidate = f"{base}-{suffix}"
            suffix += 1

    async def create(self, payload: RegionCreate) -> Region:
        name_dict = payload.name.model_dump()
        slug_seed = payload.slug or pick_locale(name_dict)
        if not slug_seed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="name must contain at least one locale",
            )
        slug = await self._resolve_slug(slugify(slug_seed))

        region = Region(
            slug=slug,
            name=name_dict,
            is_active=payload.is_active,
        )
        self.db.add(region)
        await self.db.commit()
        await self.db.refresh(region)
        return region

    async def update(self, region: Region, payload: RegionUpdate) -> Region:
        data = payload.model_dump(exclude_unset=True)
        merge_translation_fields(region, data, ("name",))

        if "slug" in data and data["slug"] is not None:
            data["slug"] = await self._resolve_slug(
                slugify(data["slug"]), exclude_id=region.id
            )
        elif "name" in data and "slug" not in data:
            data["slug"] = await self._resolve_slug(
                slugify(pick_locale(data["name"])), exclude_id=region.id
            )

        for field, value in data.items():
            setattr(region, field, value)
        await self.db.commit()
        await self.db.refresh(region)
        return region

    async def delete(self, region: Region) -> None:
        await self.db.delete(region)
        await self.db.commit()


def get_region_service(db: AsyncSession = Depends(get_db)) -> RegionService:
    return RegionService(db)
