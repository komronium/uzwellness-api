import uuid

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.db_utils import assert_fk, fetch_by_ids
from app.core.permissions import (
    SANATORIUM_SUPER_ADMIN_ONLY_FIELDS,
    assert_super_admin_only_fields,
)
from app.core.slug import resolve_unique_slug, slugify
from app.core.utils import merge_translation_fields, pick_locale
from app.models.amenity import Amenity, SanatoriumAmenity
from app.models.destination import Destination
from app.models.region import Region
from app.models.sanatorium import Sanatorium, SanatoriumStatus
from app.models.user import User
from app.schemas.sanatorium import SanatoriumCreate, SanatoriumUpdate
from app.schemas.sanatorium_reservation import SanatoriumReservationSettingsUpdate


def _slug(text: str) -> str:
    return slugify(text, fallback="sanatorium")


class SanatoriumService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, sanatorium_id: uuid.UUID) -> Sanatorium | None:
        return await self._reload(sanatorium_id)

    async def get_by_slug(self, slug: str) -> Sanatorium | None:
        obj = await self.db.scalar(select(Sanatorium).where(Sanatorium.slug == slug))
        return await self._reload(obj.id) if obj else None

    async def create(self, payload: SanatoriumCreate) -> Sanatorium:
        name_dict = payload.name.model_dump()
        slug_seed = payload.slug or pick_locale(name_dict)
        if not slug_seed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="name must contain at least one locale",
            )
        slug = await resolve_unique_slug(self.db, Sanatorium, _slug(slug_seed))

        await assert_fk(self.db, Region, payload.region_id, "region_id")
        await assert_fk(self.db, Destination, payload.destination_id, "destination_id")
        amenity_links = await self._build_amenity_links(payload.amenities)

        sanatorium = Sanatorium(
            **_create_values(payload, name=name_dict, slug=slug),
            amenity_links=amenity_links,
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
            data, actor, restricted_fields=SANATORIUM_SUPER_ADMIN_ONLY_FIELDS
        )

        amenities_provided = "amenities" in data
        data.pop("amenities", None)
        tiers = data.pop("agent_discount_tiers", _MISSING)
        policies = data.pop("policies", _MISSING)

        await self._assert_update_fks(data)
        merge_translation_fields(sanatorium, data, _TRANSLATION_FIELDS)
        await self._resolve_update_slug(sanatorium, data)

        for field, value in data.items():
            setattr(sanatorium, field, value)

        _apply_json_updates(sanatorium, payload, tiers=tiers, policies=policies)
        if amenities_provided:
            sanatorium.amenity_links = await self._build_amenity_links(
                payload.amenities or []
            )

        await self.db.commit()
        return await self._reload_required(sanatorium.id)

    async def _assert_update_fks(self, data: dict) -> None:
        if "region_id" in data:
            await assert_fk(self.db, Region, data["region_id"], "region_id")
        if "destination_id" in data:
            await assert_fk(
                self.db, Destination, data["destination_id"], "destination_id"
            )

    async def _resolve_update_slug(self, sanatorium: Sanatorium, data: dict) -> None:
        if "slug" in data and data["slug"] is not None:
            data["slug"] = await resolve_unique_slug(
                self.db, Sanatorium, _slug(data["slug"]), exclude_id=sanatorium.id
            )
        elif "name" in data and "slug" not in data:
            data["slug"] = await resolve_unique_slug(
                self.db,
                Sanatorium,
                _slug(pick_locale(data["name"])),
                exclude_id=sanatorium.id,
            )

    async def _build_amenity_links(self, items) -> list[SanatoriumAmenity]:
        if not items:
            return []
        await fetch_by_ids(
            self.db, Amenity, [i.amenity_id for i in items], label="amenity"
        )
        return [
            SanatoriumAmenity(
                amenity_id=i.amenity_id, cost=i.cost, is_available=i.is_available
            )
            for i in items
        ]

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

    async def update_reservation_settings(
        self, sanatorium: Sanatorium, payload: SanatoriumReservationSettingsUpdate
    ) -> Sanatorium:
        data = payload.model_dump(exclude_unset=True)
        for field, value in data.items():
            setattr(sanatorium, field, value)
        await self.db.commit()
        return await self._reload_required(sanatorium.id)

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
                selectinload(Sanatorium.amenity_links),
            )
        )


_TRANSLATION_FIELDS = (
    "name",
    "description",
    "address",
    "house_rules",
    "cancellation_policy",
)


def _create_values(
    payload: SanatoriumCreate, *, name: dict, slug: str
) -> dict[str, object]:
    return {
        "name": name,
        "slug": slug,
        "description": payload.description.model_dump(),
        "city": payload.city,
        "region_id": payload.region_id,
        "destination_id": payload.destination_id,
        "address": payload.address.model_dump(),
        "lat": payload.lat,
        "lng": payload.lng,
        "phones": payload.phones,
        "website": payload.website,
        "check_in_time": payload.check_in_time,
        "check_out_time": payload.check_out_time,
        "pets_allowed": payload.pets_allowed,
        "service_animals_allowed": payload.service_animals_allowed,
        "min_checkin_age": payload.min_checkin_age,
        "quiet_hours_from": payload.quiet_hours_from,
        "quiet_hours_to": payload.quiet_hours_to,
        "payment_methods": payload.payment_methods,
        "house_rules": payload.house_rules.model_dump(exclude_none=True),
        "cancellation_policy": payload.cancellation_policy.model_dump(
            exclude_none=True
        ),
        "weekly_schedule": payload.weekly_schedule,
        "stars": payload.stars,
        "property_type": payload.property_type,
        "wellness_category": payload.wellness_category,
        "treatment_focuses": payload.treatment_focuses,
        "treatment_profile": payload.treatment_profile.model_dump(),
        "year_opened": payload.year_opened,
        "languages_spoken": payload.languages_spoken,
        "highlights": payload.highlights,
        "promo_badges": [b.model_dump(mode="json") for b in payload.promo_badges],
        "surroundings": [s.model_dump() for s in payload.surroundings],
        "venues": [v.model_dump() for v in payload.venues],
        "meal_schedule": [m.model_dump() for m in payload.meal_schedule],
        "service_matrix": payload.service_matrix.model_dump(mode="json"),
        "medical_base": payload.medical_base.model_dump(),
        "policies": payload.policies.model_dump(mode="json"),
        "platform_commission_percent": payload.platform_commission_percent,
        "b2b_commission_percent": payload.b2b_commission_percent,
        "agent_discount_tiers": _agent_discount_tiers_json(
            payload.agent_discount_tiers
        ),
        "admin_user_id": payload.admin_user_id,
        "status": SanatoriumStatus.PENDING,
    }


def _apply_json_updates(
    sanatorium: Sanatorium, payload: SanatoriumUpdate, *, tiers, policies
) -> None:
    if tiers is not _MISSING:
        sanatorium.agent_discount_tiers = _agent_discount_tiers_json(tiers)

    if policies is not _MISSING:
        sanatorium.policies = (
            payload.policies.model_dump(mode="json") if payload.policies else {}
        )


_MISSING: object = object()


def _agent_discount_tiers_json(tiers) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for tier in tiers or []:
        data = tier.model_dump(mode="json") if hasattr(tier, "model_dump") else tier
        result.append(
            {
                "min_bookings": int(data["min_bookings"]),
                "discount_percent": str(data["discount_percent"]),
            }
        )
    return result


def get_sanatorium_service(db: AsyncSession = Depends(get_db)) -> SanatoriumService:
    return SanatoriumService(db)
