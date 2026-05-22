import uuid
from collections.abc import Sequence
from decimal import Decimal

from fastapi import Depends, HTTPException, status
from sqlalchemy import Numeric, case, cast, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.pagination import paginated
from app.core.slug import slugify as _slugify
from app.core.utils import merge_translation_fields, pick_locale
from app.models.destination import Destination
from app.models.room import Room
from app.models.sanatorium import Sanatorium, SanatoriumStatus
from app.schemas.destination import DestinationCreate, DestinationUpdate


def slugify(text: str) -> str:
    return _slugify(text, fallback="destination")


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
        """Return (destination, sanatoriums_count, min_price_usd) for active tiles.

        Computes the **customer-facing** weekday price per room:
        `base_price * (1 + markup_percent/100) * (1 - coalesce(discount, 0)/100)`
        — same formula as `calculate_night_price` for non-weekend nights.
        UZS rooms are normalized to USD via `usd_uzs_rate` if configured;
        otherwise they drop out of the MIN. Seasonal period overrides
        (`room_price_periods`) are intentionally skipped — tile prices
        reflect the year-round default, not a snapshot of any single date.
        """
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
                (Room.sanatorium_id == Sanatorium.id) & (Room.is_active.is_(True)),
            )
            .where(Destination.is_active.is_(True))
            .group_by(Destination.id)
            .order_by(Destination.created_at.asc())
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
        return (
            await self.db.execute(
                select(Destination).where(Destination.id == destination_id)
            )
        ).scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Destination | None:
        return (
            await self.db.execute(select(Destination).where(Destination.slug == slug))
        ).scalar_one_or_none()

    async def _resolve_slug(
        self, base: str, exclude_id: uuid.UUID | None = None
    ) -> str:
        candidate = base
        suffix = 2
        while True:
            existing = (
                await self.db.execute(
                    select(Destination).where(Destination.slug == candidate)
                )
            ).scalar_one_or_none()
            if existing is None or existing.id == exclude_id:
                return candidate
            candidate = f"{base}-{suffix}"
            suffix += 1

    async def create(self, payload: DestinationCreate) -> Destination:
        name_dict = payload.name.model_dump()
        slug_seed = payload.slug or pick_locale(name_dict)
        if not slug_seed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="name must contain at least one locale",
            )
        slug = await self._resolve_slug(slugify(slug_seed))

        destination = Destination(
            slug=slug,
            name=name_dict,
            tagline=payload.tagline.model_dump(),
            description=payload.description.model_dump(exclude_none=True),
            hero_image=payload.hero_image,
            country=payload.country,
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
            data["slug"] = await self._resolve_slug(
                slugify(data["slug"]), exclude_id=destination.id
            )
        elif "name" in data and "slug" not in data:
            data["slug"] = await self._resolve_slug(
                slugify(pick_locale(data["name"])), exclude_id=destination.id
            )

        for field, value in data.items():
            setattr(destination, field, value)
        await self.db.commit()
        await self.db.refresh(destination)
        return destination

    async def delete(self, destination: Destination) -> None:
        await self.db.delete(destination)
        await self.db.commit()


def get_destination_service(
    db: AsyncSession = Depends(get_db),
) -> DestinationService:
    return DestinationService(db)
