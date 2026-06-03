import uuid
from collections.abc import Sequence
from decimal import Decimal

from fastapi import Depends, HTTPException, status
from sqlalchemy import Numeric, case, cast, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import settings
from app.core.pagination import paginated
from app.core.slug import resolve_unique_slug, slugify
from app.core.ids import uuid7
from app.core.storage import MIME_EXTENSIONS, StorageBackend, url_to_key
from app.core.utils import merge_translation_fields, pick_locale
from app.models.destination import Destination
from app.models.room import Room
from app.models.sanatorium import Sanatorium, SanatoriumStatus
from app.schemas.destination import DestinationCreate, DestinationUpdate


def _slug(text: str) -> str:
    return slugify(text, fallback="destination")


class DestinationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_all(
        self,
        *,
        limit: int,
        offset: int,
        active_only: bool = False,
    ) -> tuple[Sequence[Destination], int]:
        stmt = select(Destination).order_by(Destination.created_at.asc())
        if active_only:
            stmt = stmt.where(Destination.is_active.is_(True))
        return await paginated(self.db, stmt, limit=limit, offset=offset)

    async def list_tiles(
        self, *, usd_uzs_rate: Decimal | None
    ) -> list[tuple[Destination, int, Decimal | None]]:
        markup_factor = literal(1) + Room.markup_percent / literal(100)
        discount_factor = literal(1) - func.coalesce(
            Room.discount_percent, literal(0)
        ) / literal(100)
        customer_price = Room.base_price * markup_factor * discount_factor

        if usd_uzs_rate and usd_uzs_rate > 0:
            rate_expr = cast(literal(usd_uzs_rate), Numeric(18, 6))
            usd_expr = case(
                (Room.base_currency == "USD", customer_price),
                (Room.base_currency == "UZS", customer_price / rate_expr),
                else_=None,
            )
        else:
            usd_expr = case(
                (Room.base_currency == "USD", customer_price),
                else_=None,
            )

        stmt = (
            select(
                Destination,
                func.count(func.distinct(Sanatorium.id)).label("sanatoriums_count"),
                func.min(usd_expr).label("min_price_usd"),
            )
            .select_from(Destination)
            .outerjoin(
                Sanatorium,
                (Sanatorium.destination_id == Destination.id)
                & (Sanatorium.status == SanatoriumStatus.APPROVED),
            )
            .outerjoin(
                Room,
                (Room.sanatorium_id == Sanatorium.id)
                & (Room.is_active.is_(True))
                & (Room.deleted_at.is_(None))
                & (Room.inventory_count > 0),
            )
            .where(Destination.is_active.is_(True))
            .group_by(Destination.id)
            .order_by(
                func.count(func.distinct(Sanatorium.id)).desc(),
                Destination.created_at.asc(),
            )
        )
        rows = (await self.db.execute(stmt)).all()
        return [
            (
                destination,
                int(count),
                Decimal(str(price)) if price is not None else None,
            )
            for destination, count, price in rows
        ]

    async def get_by_id(self, destination_id: uuid.UUID) -> Destination | None:
        return await self.db.get(Destination, destination_id)

    async def get_by_slug(self, slug: str) -> Destination | None:
        return await self.db.scalar(select(Destination).where(Destination.slug == slug))

    async def create(self, payload: DestinationCreate) -> Destination:
        name_dict = payload.name.model_dump()
        slug_seed = payload.slug or pick_locale(name_dict)
        if not slug_seed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="name must contain at least one locale",
            )
        slug = await resolve_unique_slug(self.db, Destination, _slug(slug_seed))

        destination = Destination(
            slug=slug,
            name=name_dict,
            tagline=payload.tagline.model_dump(),
            description=payload.description.model_dump(exclude_none=True),
            lat=payload.lat,
            lng=payload.lng,
            is_active=payload.is_active,
        )
        self.db.add(destination)
        await self.db.commit()
        await self.db.refresh(destination)
        return destination

    async def update(
        self, destination: Destination, payload: DestinationUpdate
    ) -> Destination:
        data = payload.model_dump(exclude_unset=True)
        merge_translation_fields(destination, data, ("name", "tagline", "description"))

        if "slug" in data and data["slug"] is not None:
            data["slug"] = await resolve_unique_slug(
                self.db, Destination, _slug(data["slug"]), exclude_id=destination.id
            )
        elif "name" in data and "slug" not in data:
            data["slug"] = await resolve_unique_slug(
                self.db,
                Destination,
                _slug(pick_locale(data["name"])),
                exclude_id=destination.id,
            )

        for field, value in data.items():
            setattr(destination, field, value)
        await self.db.commit()
        await self.db.refresh(destination)
        return destination

    async def update_hero_image(
        self,
        destination: Destination,
        *,
        content: bytes,
        content_type: str,
        storage: StorageBackend,
    ) -> Destination:
        await self._delete_local_hero_image(destination, storage)
        ext = MIME_EXTENSIONS[content_type]
        image_id = uuid7()
        key = f"destinations/{destination.id}/{image_id}.{ext}"
        destination.hero_image_url = await storage.save(
            key=key, content=content, content_type=content_type
        )
        await self.db.commit()
        await self.db.refresh(destination)
        return destination

    async def delete_hero_image(
        self, destination: Destination, storage: StorageBackend
    ) -> Destination:
        await self._delete_local_hero_image(destination, storage)
        destination.hero_image_url = None
        await self.db.commit()
        await self.db.refresh(destination)
        return destination

    async def delete(self, destination: Destination) -> None:
        await self.db.delete(destination)
        await self.db.commit()

    @staticmethod
    async def _delete_local_hero_image(
        destination: Destination, storage: StorageBackend
    ) -> None:
        url = destination.hero_image_url
        prefix = settings.UPLOAD_URL_PREFIX.rstrip("/") + "/"
        if url and url.startswith(prefix):
            await storage.delete(key=url_to_key(url))


def get_destination_service(
    db: AsyncSession = Depends(get_db),
) -> DestinationService:
    return DestinationService(db)
