import uuid
from datetime import datetime, time
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.utils import pick_locale
from app.models.sanatorium import (
    HostType,
    PropertyType,
    SanatoriumStatus,
    WellnessCategory,
)
from app.schemas.common import Page, Translations, TranslationsCreate
from app.schemas.destination import DestinationAdminRead, DestinationRead
from app.schemas.region import RegionAdminRead, RegionRead
from app.schemas.sanatorium_components import (
    MealService,
    PromoBadge,
    PromoBadgeRead,
    RatingBreakdown,
    SanatoriumAmenityAdminRead,
    SanatoriumAmenityItem,
    SanatoriumAmenityRead,
    Surrounding,
    Venue,
)
from app.schemas.sanatorium_media import SanatoriumImageRead, SanatoriumImageUpdate
from app.schemas.sanatorium_medical import (
    MedicalBase,
    MedicalBaseRead,
    TreatmentProfile,
    TreatmentProfileRead,
)
from app.schemas.sanatorium_service_matrix import (
    ServiceMatrix,
    ServiceMatrixRead,
)
from app.schemas.sanatorium_policies import SanatoriumPolicies, SanatoriumPoliciesUpdate

__all__ = ("SanatoriumImageRead", "SanatoriumImageUpdate")


class AgentDiscountTier(BaseModel):
    min_bookings: int = Field(ge=1, le=10000)
    discount_percent: Decimal = Field(ge=0, le=100)


class SanatoriumCreate(BaseModel):
    name: TranslationsCreate
    description: TranslationsCreate
    city: str = Field(min_length=1, max_length=120)
    region_id: uuid.UUID | None = None
    destination_id: uuid.UUID | None = None
    address: TranslationsCreate
    lat: Decimal | None = Field(default=None, ge=-90, le=90)
    lng: Decimal | None = Field(default=None, ge=-180, le=180)
    phones: list[str] = Field(default_factory=list, max_length=10)
    postal_code: str | None = Field(default=None, max_length=20)
    customer_support_email: str | None = Field(default=None, max_length=255)
    website: str | None = Field(default=None, max_length=255)
    check_in_time: time | None = None
    check_out_time: time | None = None
    pets_allowed: bool | None = None
    service_animals_allowed: bool | None = None
    min_checkin_age: int | None = Field(default=None, ge=0, le=120)
    quiet_hours_from: time | None = None
    quiet_hours_to: time | None = None
    payment_methods: list[str] = Field(default_factory=list)
    house_rules: Translations = Field(default_factory=Translations)
    cancellation_policy: Translations = Field(default_factory=Translations)
    weekly_schedule: dict = Field(default_factory=dict)
    stars: int = Field(ge=1, le=5)
    property_type: PropertyType = PropertyType.SANATORIUM
    wellness_category: WellnessCategory | None = None
    treatment_focuses: list[str] = Field(default_factory=list)
    treatment_profile: TreatmentProfile = Field(default_factory=TreatmentProfile)
    year_opened: int | None = Field(default=None, ge=1800, le=2100)
    renovation_year: int | None = Field(default=None, ge=1800, le=2100)
    chain_name: str | None = Field(default=None, max_length=120)
    host_type: HostType | None = None
    languages_spoken: list[str] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list)
    promo_badges: list[PromoBadge] = Field(default_factory=list)
    surroundings: list[Surrounding] = Field(default_factory=list)
    venues: list[Venue] = Field(default_factory=list)
    meal_schedule: list[MealService] = Field(default_factory=list)
    service_matrix: ServiceMatrix = Field(default_factory=ServiceMatrix)
    slug: str | None = Field(default=None, max_length=255)
    admin_user_id: uuid.UUID | None = None
    amenities: list[SanatoriumAmenityItem] = Field(default_factory=list)
    platform_commission_percent: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    b2b_commission_percent: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    agent_discount_tiers: list[AgentDiscountTier] = Field(default_factory=list)
    medical_base: MedicalBase = Field(default_factory=MedicalBase)
    policies: SanatoriumPolicies = Field(default_factory=SanatoriumPolicies)

    @field_validator("agent_discount_tiers")
    @classmethod
    def _validate_tiers(cls, value: list[AgentDiscountTier]) -> list[AgentDiscountTier]:
        return _normalize_tiers(value)


class SanatoriumUpdate(BaseModel):
    name: Translations | None = None
    slug: str | None = Field(default=None, max_length=255)
    description: Translations | None = None
    city: str | None = Field(default=None, min_length=1, max_length=120)
    region_id: uuid.UUID | None = None
    destination_id: uuid.UUID | None = None
    address: Translations | None = None
    lat: Decimal | None = Field(default=None, ge=-90, le=90)
    lng: Decimal | None = Field(default=None, ge=-180, le=180)
    phones: list[str] | None = Field(default=None, max_length=10)
    postal_code: str | None = Field(default=None, max_length=20)
    customer_support_email: str | None = Field(default=None, max_length=255)
    website: str | None = Field(default=None, max_length=255)
    check_in_time: time | None = None
    check_out_time: time | None = None
    pets_allowed: bool | None = None
    service_animals_allowed: bool | None = None
    min_checkin_age: int | None = Field(default=None, ge=0, le=120)
    quiet_hours_from: time | None = None
    quiet_hours_to: time | None = None
    payment_methods: list[str] | None = None
    house_rules: Translations | None = None
    cancellation_policy: Translations | None = None
    weekly_schedule: dict | None = None
    stars: int | None = Field(default=None, ge=1, le=5)
    property_type: PropertyType | None = None
    wellness_category: WellnessCategory | None = None
    admin_user_id: uuid.UUID | None = None
    treatment_focuses: list[str] | None = None
    treatment_profile: TreatmentProfile | None = None
    year_opened: int | None = Field(default=None, ge=1800, le=2100)
    renovation_year: int | None = Field(default=None, ge=1800, le=2100)
    chain_name: str | None = Field(default=None, max_length=120)
    host_type: HostType | None = None
    languages_spoken: list[str] | None = None
    highlights: list[str] | None = None
    is_featured: bool | None = None
    display_order: int | None = Field(default=None, ge=0)
    promo_badges: list[PromoBadge] | None = None
    surroundings: list[Surrounding] | None = None
    venues: list[Venue] | None = None
    meal_schedule: list[MealService] | None = None
    service_matrix: ServiceMatrix | None = None
    amenities: list[SanatoriumAmenityItem] | None = None
    platform_commission_percent: Decimal | None = Field(default=None, ge=0, le=100)
    b2b_commission_percent: Decimal | None = Field(default=None, ge=0, le=100)
    agent_discount_tiers: list[AgentDiscountTier] | None = None
    medical_base: MedicalBase | None = None
    policies: SanatoriumPoliciesUpdate | None = None

    @field_validator("agent_discount_tiers")
    @classmethod
    def _validate_tiers(
        cls, value: list[AgentDiscountTier] | None
    ) -> list[AgentDiscountTier] | None:
        if value is None:
            return None
        return _normalize_tiers(value)


class _SanatoriumReadCommon(BaseModel):
    id: uuid.UUID
    slug: str
    city: str
    region_id: uuid.UUID | None
    destination_id: uuid.UUID | None
    lat: Decimal | None
    lng: Decimal | None
    phones: list[str]
    postal_code: str | None
    customer_support_email: str | None
    website: str | None
    check_in_time: time | None
    check_out_time: time | None
    pets_allowed: bool | None
    service_animals_allowed: bool | None
    min_checkin_age: int | None
    quiet_hours_from: time | None
    quiet_hours_to: time | None
    payment_methods: list[str]
    weekly_schedule: dict
    stars: int
    status: SanatoriumStatus
    property_type: PropertyType
    wellness_category: WellnessCategory | None
    treatment_focuses: list[str]
    treatment_profile: TreatmentProfileRead
    year_opened: int | None
    renovation_year: int | None
    chain_name: str | None
    host_type: HostType | None
    languages_spoken: list[str]
    highlights: list[str]
    is_featured: bool
    display_order: int
    promo_badges: list[PromoBadgeRead] = Field(default_factory=list)
    surroundings: list[Surrounding]
    venues: list[Venue]
    meal_schedule: list[MealService]
    service_matrix: ServiceMatrixRead
    avg_rating: Decimal | None
    review_count: int
    rating_breakdown: RatingBreakdown = Field(default_factory=RatingBreakdown)
    admin_user_id: uuid.UUID | None
    platform_commission_percent: Decimal
    b2b_commission_percent: Decimal
    agent_discount_tiers: list[AgentDiscountTier] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    images: list[SanatoriumImageRead] = Field(default_factory=list)


class SanatoriumRead(_SanatoriumReadCommon):
    name: str
    description: str
    address: str
    house_rules: str
    cancellation_policy: str
    region: RegionRead | None = None
    destination: DestinationRead | None = None
    amenities: list[SanatoriumAmenityRead] = Field(default_factory=list)
    medical_base: MedicalBaseRead
    policies: SanatoriumPolicies

    @classmethod
    def from_obj(cls, obj, locale: str) -> "SanatoriumRead":
        return cls(
            **_public_core(obj, locale),
            **_public_detail(obj, locale),
            **_public_relations(obj, locale),
        )


class SanatoriumAdminRead(_SanatoriumReadCommon):
    model_config = ConfigDict(from_attributes=True)

    name: dict
    description: dict
    address: dict
    house_rules: dict
    cancellation_policy: dict
    region: RegionAdminRead | None = None
    destination: DestinationAdminRead | None = None
    amenities: list[SanatoriumAmenityAdminRead] = Field(
        default_factory=list, validation_alias="amenity_links"
    )
    promo_badges: list[PromoBadge] = Field(default_factory=list)
    medical_base: MedicalBase
    policies: SanatoriumPolicies
    treatment_profile: TreatmentProfile
    service_matrix: ServiceMatrix


class SanatoriumList(Page[SanatoriumRead]):
    pass


class SanatoriumAdminList(Page[SanatoriumAdminRead]):
    pass


def _public_core(obj, locale: str) -> dict:
    return {
        "id": obj.id,
        "slug": obj.slug,
        "name": pick_locale(obj.name, locale),
        "description": pick_locale(obj.description, locale),
        "city": obj.city,
        "region_id": obj.region_id,
        "destination_id": obj.destination_id,
        "address": pick_locale(obj.address, locale),
        "lat": obj.lat,
        "lng": obj.lng,
        "phones": _phones(obj.phones),
        "postal_code": obj.postal_code,
        "customer_support_email": obj.customer_support_email,
        "website": obj.website,
        "stars": obj.stars,
        "status": obj.status,
        "created_at": obj.created_at,
        "updated_at": obj.updated_at,
    }


def _public_detail(obj, locale: str) -> dict:
    return {
        "check_in_time": obj.check_in_time,
        "check_out_time": obj.check_out_time,
        "pets_allowed": obj.pets_allowed,
        "service_animals_allowed": obj.service_animals_allowed,
        "min_checkin_age": obj.min_checkin_age,
        "quiet_hours_from": obj.quiet_hours_from,
        "quiet_hours_to": obj.quiet_hours_to,
        "payment_methods": obj.payment_methods,
        "house_rules": pick_locale(obj.house_rules, locale),
        "cancellation_policy": pick_locale(obj.cancellation_policy, locale),
        "weekly_schedule": obj.weekly_schedule,
        "property_type": obj.property_type,
        "wellness_category": obj.wellness_category,
        "treatment_focuses": obj.treatment_focuses,
        "year_opened": obj.year_opened,
        "renovation_year": obj.renovation_year,
        "chain_name": obj.chain_name,
        "host_type": obj.host_type,
        "languages_spoken": obj.languages_spoken,
        "highlights": obj.highlights,
        "is_featured": obj.is_featured,
        "display_order": obj.display_order,
        "surroundings": _surroundings(obj.surroundings),
        "venues": _venues(obj.venues),
        "meal_schedule": _meal_schedule(obj.meal_schedule),
        "avg_rating": obj.avg_rating,
        "review_count": obj.review_count,
        "admin_user_id": obj.admin_user_id,
        "platform_commission_percent": obj.platform_commission_percent,
        "b2b_commission_percent": obj.b2b_commission_percent,
    }


def _public_relations(obj, locale: str) -> dict:
    return {
        "region": RegionRead.from_obj(obj.region, locale) if obj.region else None,
        "destination": (
            DestinationRead.from_obj(obj.destination, locale)
            if obj.destination
            else None
        ),
        "treatment_profile": TreatmentProfileRead.from_obj(
            obj.treatment_profile, locale
        ),
        "promo_badges": _active_promo_badges(obj, locale),
        "service_matrix": ServiceMatrixRead.from_obj(obj.service_matrix, locale),
        "rating_breakdown": RatingBreakdown(**(obj.rating_breakdown or {})),
        "agent_discount_tiers": [
            AgentDiscountTier(**t) for t in (obj.agent_discount_tiers or [])
        ],
        "images": [SanatoriumImageRead.model_validate(i) for i in obj.images],
        "amenities": [
            SanatoriumAmenityRead.from_obj(link, locale) for link in obj.amenity_links
        ],
        "medical_base": MedicalBaseRead.from_obj(obj.medical_base, locale),
        "policies": SanatoriumPolicies.model_validate(obj.policies or {}),
    }


def _active_promo_badges(obj, locale: str) -> list[PromoBadgeRead]:
    return [
        PromoBadgeRead.from_obj(badge, locale)
        for badge in (obj.promo_badges or [])
        if (badge.get("is_active", True) if isinstance(badge, dict) else True)
    ]


def _phones(value: Any) -> list[str]:
    result: list[str] = []
    for item in value or []:
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, dict):
            phone = item.get("phone") or item.get("number") or item.get("value")
            if phone:
                result.append(str(phone))
    return result


def _surroundings(value: Any) -> list[dict]:
    result: list[dict] = []
    for item in value or []:
        if not isinstance(item, dict):
            continue
        distance_m = item.get("distance_m")
        if distance_m is None:
            distance_m = _distance_to_meters(item.get("distance"))
        result.append(
            {
                "name": str(item.get("name") or ""),
                "type": str(item.get("type") or "point_of_interest"),
                "distance_m": max(int(distance_m or 0), 0),
            }
        )
    return [item for item in result if item["name"]]


def _venues(value: Any) -> list[dict]:
    result: list[dict] = []
    for item in value or []:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not name:
            continue
        result.append(
            {
                "name": str(name),
                "type": str(item.get("type") or "general"),
                "building": item.get("building"),
                "hours": item.get("hours"),
            }
        )
    return result


def _meal_schedule(value: Any) -> list[dict]:
    result: list[dict] = []
    for item in value or []:
        if not isinstance(item, dict):
            continue
        time_from = item.get("time_from")
        time_to = item.get("time_to")
        if (not time_from or not time_to) and isinstance(item.get("time"), str):
            time_from, time_to = _split_time_range(item["time"])
        meal = item.get("meal") or item.get("name")
        if meal and time_from and time_to:
            result.append(
                {
                    "meal": str(meal).lower(),
                    "time_from": time_from,
                    "time_to": time_to,
                    "style": item.get("style") or item.get("board"),
                }
            )
    return result


def _distance_to_meters(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, int | float | Decimal):
        return int(value)
    text = str(value).lower().replace("approx.", "").strip()
    if "near" in text:
        return 0
    number = "".join(char for char in text if char.isdigit() or char == ".")
    if not number:
        return 0
    meters = float(number)
    if "km" in text:
        meters *= 1000
    return int(meters)


def _split_time_range(value: str) -> tuple[str | None, str | None]:
    if "-" not in value:
        return None, None
    start, end = [part.strip() for part in value.split("-", 1)]
    return (start or None), (end or None)


def _normalize_tiers(value: list[AgentDiscountTier]) -> list[AgentDiscountTier]:
    if not value:
        return []
    seen: set[int] = set()
    for tier in value:
        if tier.min_bookings in seen:
            raise ValueError(
                f"Duplicate min_bookings={tier.min_bookings} in agent_discount_tiers"
            )
        seen.add(tier.min_bookings)
    return sorted(value, key=lambda t: t.min_bookings)
