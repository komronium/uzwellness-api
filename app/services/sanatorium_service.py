import uuid
from collections.abc import Sequence
from decimal import Decimal

from fastapi import Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.db_utils import assert_fk
from app.core.permissions import (
    SANATORIUM_SUPER_ADMIN_ONLY_FIELDS,
    assert_super_admin_only_fields,
)
from app.core.policies import SanatoriumPolicy
from app.core.slug import slugify as _slugify
from app.core.utils import merge_translation_fields, pick_locale
from app.models.amenity import Amenity
from app.models.destination import Destination
from app.models.region import Region
from app.models.sanatorium import (
    PropertyType,
    Sanatorium,
    SanatoriumStatus,
    WellnessCategory,
)
from app.models.user import User, UserRole
from app.schemas.sanatorium import SanatoriumCreate, SanatoriumUpdate


def slugify(text: str) -> str:
    return _slugify(text, fallback="sanatorium")


class SanatoriumService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, sanatorium_id: uuid.UUID) -> Sanatorium | None:
        return await self._reload(sanatorium_id)

    async def get_by_slug(self, slug: str) -> Sanatorium | None:
        obj = await self.db.scalar(
            select(Sanatorium).where(Sanatorium.slug == slug)
        )
        return await self._reload(obj.id) if obj else None

    async def _resolve_slug(
        self, base: str, exclude_id: uuid.UUID | None = None
    ) -> str:
        candidate = base
        suffix = 2
        while True:
            existing = await self.db.scalar(
                select(Sanatorium).where(Sanatorium.slug == candidate)
            )
            if existing is None or existing.id == exclude_id:
                return candidate
            candidate = f"{base}-{suffix}"
            suffix += 1

    async def create(self, payload: SanatoriumCreate) -> Sanatorium:
        name_dict = payload.name.model_dump()
        slug_seed = payload.slug or pick_locale(name_dict)
        if not slug_seed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="name must contain at least one locale",
            )
        base_slug = slugify(slug_seed)
        slug = await self._resolve_slug(base_slug)

        await assert_fk(self.db, Region, payload.region_id, "region_id")
        await assert_fk(self.db, Destination, payload.destination_id, "destination_id")
        amenities = await self._fetch_amenities(payload.amenity_ids)

        sanatorium = Sanatorium(
            name=name_dict,
            slug=slug,
            description=payload.description.model_dump(),
            city=payload.city,
            region_id=payload.region_id,
            destination_id=payload.destination_id,
            address=payload.address.model_dump(),
            lat=payload.lat,
            lng=payload.lng,
            phones=payload.phones,
            website=payload.website,
            check_in_time=payload.check_in_time,
            check_out_time=payload.check_out_time,
            payment_methods=payload.payment_methods,
            house_rules=payload.house_rules.model_dump(exclude_none=True),
            cancellation_policy=payload.cancellation_policy.model_dump(
                exclude_none=True
            ),
            weekly_schedule=payload.weekly_schedule,
            stars=payload.stars,
            property_type=payload.property_type,
            wellness_category=payload.wellness_category,
            treatment_focuses=payload.treatment_focuses,
            platform_commission_percent=payload.platform_commission_percent,
            b2b_commission_percent=payload.b2b_commission_percent,
            agent_discount_tiers=[
                t.model_dump(mode="json") for t in payload.agent_discount_tiers
            ],
            admin_user_id=payload.admin_user_id,
            status=SanatoriumStatus.PENDING,
            amenities=amenities,
        )
        self.db.add(sanatorium)
        await self.db.commit()
        return await self._reload_required(sanatorium.id)

    async def update(
        self,
        sanatorium: Sanatorium,
        payload: SanatoriumUpdate,
        *,
        actor: User | None = None,
    ) -> Sanatorium:
        data = payload.model_dump(exclude_unset=True)

        assert_super_admin_only_fields(
            data, actor, allowed_fields=SANATORIUM_SUPER_ADMIN_ONLY_FIELDS
        )

        amenity_ids = data.pop("amenity_ids", None)
        tiers = data.pop("agent_discount_tiers", _MISSING)

        if "region_id" in data:
            await assert_fk(self.db, Region, data["region_id"], "region_id")
        if "destination_id" in data:
            await assert_fk(
                self.db, Destination, data["destination_id"], "destination_id"
            )

        merge_translation_fields(
            sanatorium,
            data,
            ("name", "description", "address", "house_rules", "cancellation_policy"),
        )

        if "slug" in data and data["slug"] is not None:
            base_slug = slugify(data["slug"])
            data["slug"] = await self._resolve_slug(base_slug, exclude_id=sanatorium.id)
        elif "name" in data and "slug" not in data:
            base_slug = slugify(pick_locale(data["name"]))
            data["slug"] = await self._resolve_slug(base_slug, exclude_id=sanatorium.id)

        for field, value in data.items():
            setattr(sanatorium, field, value)

        if tiers is not _MISSING:
            # payload.model_dump() already converted Pydantic models to dicts; we
            # just need to coerce the Decimal in discount_percent to str so JSONB
            # round-trips cleanly.
            sanatorium.agent_discount_tiers = [
                {
                    "min_bookings": int(t["min_bookings"]),
                    "discount_percent": str(t["discount_percent"]),
                }
                for t in (tiers or [])
            ]

        if amenity_ids is not None:
            sanatorium.amenities = await self._fetch_amenities(amenity_ids)

        await self.db.commit()
        return await self._reload_required(sanatorium.id)

    async def approve(self, sanatorium: Sanatorium) -> Sanatorium:
        if sanatorium.status == SanatoriumStatus.APPROVED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Sanatorium already approved",
            )
        sanatorium.status = SanatoriumStatus.APPROVED
        await self.db.commit()
        return await self._reload_required(sanatorium.id)

    async def reject(self, sanatorium: Sanatorium) -> Sanatorium:
        if sanatorium.status == SanatoriumStatus.REJECTED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Sanatorium already rejected",
            )
        sanatorium.status = SanatoriumStatus.REJECTED
        await self.db.commit()
        return await self._reload_required(sanatorium.id)

    async def get_visible(
        self, sanatorium_id: uuid.UUID, user: User | None
    ) -> Sanatorium | None:
        sanatorium = await self.get_by_id(sanatorium_id)
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
            for aid in amenity_ids:
                sub = (
                    select(Sanatorium.id)
                    .join(Sanatorium.amenities)
                    .where(Amenity.id == aid)
                    .scalar_subquery()
                )
                base = base.where(Sanatorium.id.in_(sub))

        total = await self.db.scalar(
            select(func.count()).select_from(base.subquery())
        )

        stmt = (
            base.options(
                selectinload(Sanatorium.images),
                selectinload(Sanatorium.amenities),
            )
            .order_by(_resolve_sort(sort, locale))
            .limit(limit)
            .offset(offset)
        )
        rows = (await self.db.scalars(stmt)).all()
        return rows, total or 0

    async def _reload_required(self, sanatorium_id: uuid.UUID) -> Sanatorium:
        result = await self._reload(sanatorium_id)
        if result is None:
            raise RuntimeError(f"Sanatorium {sanatorium_id} not found after write")
        return result

    async def _reload(self, sanatorium_id: uuid.UUID) -> Sanatorium | None:
        return await self.db.scalar(
            select(Sanatorium)
            .where(Sanatorium.id == sanatorium_id)
            .options(
                selectinload(Sanatorium.images),
                selectinload(Sanatorium.amenities),
            )
        )

    async def _fetch_amenities(self, amenity_ids: list[uuid.UUID]) -> list[Amenity]:
        if not amenity_ids:
            return []
        rows = (
            await self.db.scalars(select(Amenity).where(Amenity.id.in_(amenity_ids)))
        ).all()
        if len(rows) != len(amenity_ids):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="One or more amenity IDs not found",
            )
        return list(rows)


_MISSING: object = object()


_STATIC_SORT_CLAUSES = {
    "stars": Sanatorium.stars.asc(),
    "-stars": Sanatorium.stars.desc(),
    "rating": Sanatorium.avg_rating.asc(),
    "-rating": Sanatorium.avg_rating.desc(),
    "created_at": Sanatorium.created_at.asc(),
    "-created_at": Sanatorium.created_at.desc(),
}

SORT_FIELDS: tuple[str, ...] = ("name", "-name", *_STATIC_SORT_CLAUSES.keys())


def _name_locale_expr(locale: str):
    """Coalesce name across locales, preferring the request locale.

    Returns a SQL expression that picks the first non-null translation
    in the order: requested locale → uz → ru → en.
    """
    fallbacks: list[str] = []
    for key in (locale, "uz", "ru", "en"):
        if key not in fallbacks:
            fallbacks.append(key)
    return func.coalesce(*[Sanatorium.name[k].astext for k in fallbacks])


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


def get_sanatorium_service(db: AsyncSession = Depends(get_db)) -> SanatoriumService:
    return SanatoriumService(db)
