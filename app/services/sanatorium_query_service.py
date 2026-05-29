import uuid
from collections.abc import Sequence
from decimal import Decimal

from fastapi import Depends
from sqlalchemy import Numeric, case, cast, func, literal, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.policies import SanatoriumPolicy
from app.models.amenity import SanatoriumAmenity
from app.models.room import Room
from app.models.sanatorium import (
    PropertyType,
    Sanatorium,
    SanatoriumStatus,
    WellnessCategory,
)
from app.models.user import User, UserRole


class SanatoriumQueryService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, sanatorium_id: uuid.UUID) -> Sanatorium | None:
        return await self._reload(sanatorium_id)

    async def get_by_slug(self, slug: str) -> Sanatorium | None:
        obj = await self.db.scalar(select(Sanatorium).where(Sanatorium.slug == slug))
        return await self._reload(obj.id) if obj else None

    async def get_visible(
        self, sanatorium_id: uuid.UUID, user: User | None
    ) -> Sanatorium | None:
        sanatorium = await self.get_by_id(sanatorium_id)
        if sanatorium is None or not SanatoriumPolicy.can_view(sanatorium, user):
            return None
        return sanatorium

    async def get_visible_by_slug(
        self, slug: str, user: User | None
    ) -> Sanatorium | None:
        sanatorium = await self.get_by_slug(slug)
        if sanatorium is None or not SanatoriumPolicy.can_view(sanatorium, user):
            return None
        return sanatorium

    async def list_for_user(
        self,
        *,
        user: User | None,
        limit: int,
        offset: int,
        city: str | None = None,
        region_id: uuid.UUID | None = None,
        destination_id: uuid.UUID | None = None,
        status_filter: SanatoriumStatus | None = None,
        stars: int | None = None,
        min_rating: Decimal | None = None,
        q: str | None = None,
        sort: str = "-created_at",
        locale: str = "en",
        amenity_ids: list[uuid.UUID] | None = None,
        treatment_focus: str | None = None,
        property_type: PropertyType | None = None,
        wellness_category: WellnessCategory | None = None,
    ) -> tuple[Sequence[Sanatorium], int]:
        base = select(Sanatorium)
        base = _apply_visibility(base, user)

        if property_type is not None:
            base = base.where(Sanatorium.property_type == property_type)
        if wellness_category is not None:
            base = base.where(Sanatorium.wellness_category == wellness_category)
        if city is not None:
            base = base.where(Sanatorium.city == city)
        if region_id is not None:
            base = base.where(Sanatorium.region_id == region_id)
        if destination_id is not None:
            base = base.where(Sanatorium.destination_id == destination_id)
        if status_filter is not None:
            base = base.where(Sanatorium.status == status_filter)
        if stars is not None:
            base = base.where(Sanatorium.stars == stars)
        if min_rating is not None:
            base = base.where(Sanatorium.avg_rating >= min_rating)
        if q is not None and q.strip():
            term = q.strip()
            base = base.where(
                Sanatorium.name["uz"].astext.icontains(term, autoescape=True)
                | Sanatorium.name["ru"].astext.icontains(term, autoescape=True)
                | Sanatorium.name["en"].astext.icontains(term, autoescape=True)
            )
        if treatment_focus is not None:
            base = base.where(Sanatorium.treatment_focuses.contains([treatment_focus]))
        if amenity_ids:
            for amenity_id in amenity_ids:
                subquery = (
                    select(SanatoriumAmenity.sanatorium_id)
                    .where(SanatoriumAmenity.amenity_id == amenity_id)
                    .scalar_subquery()
                )
                base = base.where(Sanatorium.id.in_(subquery))

        total = await self._count(base)
        stmt = (
            base.options(
                selectinload(Sanatorium.images),
                selectinload(Sanatorium.amenity_links),
            )
            .order_by(_resolve_sort(sort, locale))
            .limit(limit)
            .offset(offset)
        )
        rows = (await self.db.scalars(stmt)).all()
        return rows, total

    async def list_featured(
        self,
        *,
        limit: int,
        offset: int,
        usd_uzs_rate: Decimal | None,
    ) -> tuple[list[tuple[Sanatorium, Decimal | None, str | None, Decimal | None]], int]:
        price_subquery = _featured_price_subquery(usd_uzs_rate)
        base = (
            select(Sanatorium)
            .where(
                Sanatorium.status == SanatoriumStatus.APPROVED,
                Sanatorium.is_featured.is_(True),
            )
            .outerjoin(
                price_subquery, price_subquery.c.sanatorium_id == Sanatorium.id
            )
        )
        total = await self._count(base)

        stmt = (
            select(
                Sanatorium,
                price_subquery.c.min_price,
                price_subquery.c.min_price_currency,
                price_subquery.c.min_price_usd,
            )
            .where(
                Sanatorium.status == SanatoriumStatus.APPROVED,
                Sanatorium.is_featured.is_(True),
            )
            .outerjoin(
                price_subquery, price_subquery.c.sanatorium_id == Sanatorium.id
            )
            .options(
                selectinload(Sanatorium.images),
                selectinload(Sanatorium.region),
                selectinload(Sanatorium.destination),
            )
            .order_by(
                Sanatorium.display_order.asc(),
                Sanatorium.avg_rating.desc().nullslast(),
                Sanatorium.created_at.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        rows = (await self.db.execute(stmt)).all()
        return [
            (
                sanatorium,
                Decimal(str(min_price)) if min_price is not None else None,
                currency,
                Decimal(str(min_price_usd)) if min_price_usd is not None else None,
            )
            for sanatorium, min_price, currency, min_price_usd in rows
        ], total

    async def _count(self, stmt) -> int:
        count_subquery = (
            stmt.order_by(None)
            .with_only_columns(literal_column("1"), maintain_column_froms=True)
            .subquery()
        )
        total = await self.db.scalar(select(func.count()).select_from(count_subquery))
        return total or 0

    async def _reload(self, sanatorium_id: uuid.UUID) -> Sanatorium | None:
        return await self.db.scalar(
            select(Sanatorium)
            .where(Sanatorium.id == sanatorium_id)
            .options(
                selectinload(Sanatorium.images),
                selectinload(Sanatorium.amenity_links),
            )
        )


_STATIC_SORT_CLAUSES = {
    "stars": Sanatorium.stars.asc(),
    "-stars": Sanatorium.stars.desc(),
    "rating": Sanatorium.avg_rating.asc(),
    "-rating": Sanatorium.avg_rating.desc(),
    "created_at": Sanatorium.created_at.asc(),
    "-created_at": Sanatorium.created_at.desc(),
}


def _name_locale_expr(locale: str):
    fallbacks: list[str] = []
    for key in (locale, "uz", "ru", "en"):
        if key not in fallbacks:
            fallbacks.append(key)
    return func.coalesce(*[Sanatorium.name[key].astext for key in fallbacks])


def _resolve_sort(sort: str, locale: str):
    if sort == "name":
        return _name_locale_expr(locale).asc()
    if sort == "-name":
        return _name_locale_expr(locale).desc()
    return _STATIC_SORT_CLAUSES.get(sort, Sanatorium.created_at.desc())


def _apply_visibility(stmt, user: User | None):
    if user is not None and user.role == UserRole.SUPER_ADMIN:
        return stmt
    if user is not None and user.role == UserRole.ADMIN:
        return stmt.where(
            (Sanatorium.status == SanatoriumStatus.APPROVED)
            | (Sanatorium.admin_user_id == user.id)
        )
    return stmt.where(Sanatorium.status == SanatoriumStatus.APPROVED)


def _featured_price_subquery(usd_uzs_rate: Decimal | None):
    price_expr = _customer_price_expr()
    usd_expr = _usd_price_expr(price_expr, usd_uzs_rate)
    ranked_room_prices = (
        select(
            Room.sanatorium_id.label("sanatorium_id"),
            price_expr.label("min_price"),
            Room.base_currency.label("min_price_currency"),
            usd_expr.label("min_price_usd"),
            func.row_number()
            .over(
                partition_by=Room.sanatorium_id,
                order_by=(
                    usd_expr.asc().nullslast(),
                    price_expr.asc(),
                    Room.created_at.asc(),
                    Room.id.asc(),
                ),
            )
            .label("rank"),
        )
        .where(Room.is_active.is_(True), Room.inventory_count > 0)
        .subquery()
    )
    return (
        select(
            ranked_room_prices.c.sanatorium_id,
            ranked_room_prices.c.min_price,
            ranked_room_prices.c.min_price_currency,
            ranked_room_prices.c.min_price_usd,
        )
        .where(ranked_room_prices.c.rank == 1)
        .subquery()
    )


def _customer_price_expr():
    markup_factor = literal(1) + Room.markup_percent / literal(100)
    discount_factor = literal(1) - func.coalesce(
        Room.discount_percent, literal(0)
    ) / literal(100)
    return Room.base_price * markup_factor * discount_factor


def _usd_price_expr(price_expr, usd_uzs_rate: Decimal | None):
    if usd_uzs_rate and usd_uzs_rate > 0:
        rate_expr = cast(literal(usd_uzs_rate), Numeric(18, 6))
        return case(
            (Room.base_currency == "USD", price_expr),
            (Room.base_currency == "UZS", price_expr / rate_expr),
            else_=None,
        )
    return case((Room.base_currency == "USD", price_expr), else_=None)


def get_sanatorium_query_service(
    db: AsyncSession = Depends(get_db),
) -> SanatoriumQueryService:
    return SanatoriumQueryService(db)
