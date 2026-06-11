import uuid
from collections.abc import Sequence
from decimal import Decimal

from fastapi import Depends
from sqlalchemy import Numeric, case, cast, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.pagination import count_query
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
        base = _apply_visibility(select(Sanatorium), user)
        base = _apply_list_filters(
            base,
            city=city,
            region_id=region_id,
            destination_id=destination_id,
            status_filter=status_filter,
            stars=stars,
            min_rating=min_rating,
            q=q,
            amenity_ids=amenity_ids,
            treatment_focus=treatment_focus,
            property_type=property_type,
            wellness_category=wellness_category,
        )
        total = await self._count(base)
        stmt = _list_statement(
            base, sort=sort, locale=locale, limit=limit, offset=offset
        )
        rows = (await self.db.scalars(stmt)).all()
        return rows, total

    async def list_featured(
        self,
        *,
        limit: int,
        offset: int,
        rates_to_uzs: dict[str, Decimal],
    ) -> tuple[
        list[tuple[Sanatorium, Decimal | None, str | None, Decimal | None]], int
    ]:
        price_subquery = _featured_price_subquery(rates_to_uzs)
        base = (
            select(Sanatorium)
            .where(
                Sanatorium.status == SanatoriumStatus.APPROVED,
                Sanatorium.is_featured.is_(True),
            )
            .outerjoin(price_subquery, price_subquery.c.sanatorium_id == Sanatorium.id)
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
            .outerjoin(price_subquery, price_subquery.c.sanatorium_id == Sanatorium.id)
            .options(
                selectinload(Sanatorium.images),
                selectinload(Sanatorium.region),
                selectinload(Sanatorium.destination),
                selectinload(Sanatorium.amenity_links).selectinload(
                    SanatoriumAmenity.amenity
                ),
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
        return await count_query(self.db, stmt)

    async def _reload(self, sanatorium_id: uuid.UUID) -> Sanatorium | None:
        return await self.db.scalar(
            select(Sanatorium)
            .where(Sanatorium.id == sanatorium_id)
            .options(
                selectinload(Sanatorium.images),
                selectinload(Sanatorium.amenity_links).selectinload(
                    SanatoriumAmenity.amenity
                ),
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


def _apply_list_filters(
    stmt,
    *,
    city: str | None,
    region_id: uuid.UUID | None,
    destination_id: uuid.UUID | None,
    status_filter: SanatoriumStatus | None,
    stars: int | None,
    min_rating: Decimal | None,
    q: str | None,
    amenity_ids: list[uuid.UUID] | None,
    treatment_focus: str | None,
    property_type: PropertyType | None,
    wellness_category: WellnessCategory | None,
):
    filters = [
        Sanatorium.property_type == property_type
        if property_type is not None
        else None,
        Sanatorium.wellness_category == wellness_category
        if wellness_category is not None
        else None,
        Sanatorium.city == city if city is not None else None,
        Sanatorium.region_id == region_id if region_id is not None else None,
        Sanatorium.destination_id == destination_id
        if destination_id is not None
        else None,
        Sanatorium.status == status_filter if status_filter is not None else None,
        Sanatorium.stars == stars if stars is not None else None,
        Sanatorium.avg_rating >= min_rating if min_rating is not None else None,
        Sanatorium.treatment_focuses.contains([treatment_focus])
        if treatment_focus is not None
        else None,
        _name_search_clause(q),
    ]
    for clause in filters:
        if clause is not None:
            stmt = stmt.where(clause)
    return _apply_amenity_filters(stmt, amenity_ids)


def _name_search_clause(q: str | None):
    if q is None or not q.strip():
        return None
    term = q.strip()
    return (
        Sanatorium.name["uz"].astext.icontains(term, autoescape=True)
        | Sanatorium.name["ru"].astext.icontains(term, autoescape=True)
        | Sanatorium.name["en"].astext.icontains(term, autoescape=True)
    )


def _apply_amenity_filters(stmt, amenity_ids: list[uuid.UUID] | None):
    for amenity_id in amenity_ids or []:
        subquery = (
            select(SanatoriumAmenity.sanatorium_id)
            .where(SanatoriumAmenity.amenity_id == amenity_id)
            .scalar_subquery()
        )
        stmt = stmt.where(Sanatorium.id.in_(subquery))
    return stmt


def _list_statement(stmt, *, sort: str, locale: str, limit: int, offset: int):
    return (
        stmt.options(
            selectinload(Sanatorium.images),
            selectinload(Sanatorium.amenity_links).selectinload(
                SanatoriumAmenity.amenity
            ),
        )
        .order_by(_resolve_sort(sort, locale))
        .limit(limit)
        .offset(offset)
    )


def _featured_price_subquery(rates_to_uzs: dict[str, Decimal]):
    price_expr = _customer_price_expr()
    usd_expr = _usd_price_expr(price_expr, rates_to_uzs)
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
        .where(
            Room.is_active.is_(True),
            Room.deleted_at.is_(None),
            Room.inventory_count > 0,
        )
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


def _usd_price_expr(price_expr, rates_to_uzs: dict[str, Decimal]):
    usd_rate = rates_to_uzs.get("USD_UZS")
    if usd_rate is None or usd_rate <= 0:
        return case((Room.base_currency == "USD", price_expr), else_=None)

    usd_rate_expr = cast(literal(usd_rate), Numeric(18, 6))
    whens = [
        (Room.base_currency == "USD", price_expr),
        (Room.base_currency == "UZS", price_expr / usd_rate_expr),
    ]
    for pair, rate in sorted(rates_to_uzs.items()):
        currency, _, quote = pair.partition("_")
        if quote != "UZS" or currency in {"USD", "UZS"} or rate <= 0:
            continue
        rate_expr = cast(literal(rate), Numeric(18, 6))
        whens.append(
            (Room.base_currency == currency, price_expr * rate_expr / usd_rate_expr)
        )
    return case(*whens, else_=None)


def get_sanatorium_query_service(
    db: AsyncSession = Depends(get_db),
) -> SanatoriumQueryService:
    return SanatoriumQueryService(db)
