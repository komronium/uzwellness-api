import uuid
from datetime import datetime, time
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.utils import pick_locale
from app.models.amenity import AmenityCost
from app.models.sanatorium import PropertyType, SanatoriumStatus, WellnessCategory
from app.schemas.amenity import AmenityAdminRead, AmenityRead
from app.schemas.common import Translations, TranslationsCreate
from app.schemas.destination import DestinationAdminRead, DestinationRead
from app.schemas.region import RegionAdminRead, RegionRead
from app.schemas.sanatorium_medical import (
    MedicalBase,
    MedicalBaseRead,
    ServiceMatrix,
    ServiceMatrixRead,
    TreatmentProfile,
    TreatmentProfileRead,
)
from app.schemas.sanatorium_policies import SanatoriumPolicies


class AgentDiscountTier(BaseModel):
    min_bookings: int = Field(ge=1, le=10000)
    discount_percent: Decimal = Field(ge=0, le=100)


TREATMENT_FOCUS_VALUES = frozenset(
    {
        "cardiovascular",
        "digestive",
        "musculoskeletal",
        "respiratory",
        "neurological",
        "dermatology",
        "endocrine",
        "wellness",
    }
)

PAYMENT_METHOD_VALUES = frozenset(
    {
        "cash",
        "bank_transfer",
        "uzcard",
        "visa",
        "mastercard",
        "jcb",
        "unionpay",
        "mir",
    }
)


class SanatoriumImageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    url: str
    order: int
    is_primary: bool
    is_360: bool
    category: str | None
    caption: str | None
    caption_i18n: dict
    alt_text: dict
    tags: list[str]
    created_at: datetime


class SanatoriumImageUpdate(BaseModel):
    is_primary: bool | None = None
    is_360: bool | None = None
    category: str | None = Field(default=None, max_length=40)
    order: int | None = Field(default=None, ge=0)
    caption: str | None = Field(default=None, max_length=255)
    caption_i18n: Translations | None = None
    alt_text: Translations | None = None
    tags: list[str] | None = None


class SanatoriumAmenityItem(BaseModel):
    amenity_id: uuid.UUID
    cost: AmenityCost = AmenityCost.FREE
    is_available: bool = True


class SanatoriumAmenityRead(BaseModel):
    cost: AmenityCost
    is_available: bool
    amenity: AmenityRead

    @classmethod
    def from_obj(cls, link, locale: str) -> "SanatoriumAmenityRead":
        return cls(
            cost=link.cost,
            is_available=link.is_available,
            amenity=AmenityRead.from_obj(link.amenity, locale),
        )


class SanatoriumAmenityAdminRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    cost: AmenityCost
    is_available: bool
    amenity: AmenityAdminRead


class Surrounding(BaseModel):
    """A nearby point of interest, e.g. 'Chor Minor Monument, attraction, 440m'."""

    name: str = Field(min_length=1, max_length=200)
    type: str = Field(min_length=1, max_length=40)
    distance_m: int = Field(ge=0)


class Venue(BaseModel):
    """An on-site venue, e.g. 'Charlston restaurant (buffet) in Blue House'."""

    name: str = Field(min_length=1, max_length=120)
    type: str = Field(min_length=1, max_length=40)
    building: str | None = Field(default=None, max_length=120)
    hours: str | None = Field(default=None, max_length=120)


_HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"


class MealService(BaseModel):
    """A meal serving window, e.g. 'breakfast 07:30-10:30 buffet'."""

    meal: str = Field(min_length=1, max_length=40)
    time_from: str = Field(pattern=_HHMM)
    time_to: str = Field(pattern=_HHMM)
    style: str | None = Field(default=None, max_length=40)


class PromoBadge(BaseModel):
    code: str = Field(..., min_length=1, max_length=80)
    kind: str = Field(default="info", min_length=1, max_length=40)
    title: Translations = Field(default_factory=Translations)
    description: Translations = Field(default_factory=Translations)
    icon: str | None = Field(default=None, max_length=100)
    is_active: bool = True
    priority: int = Field(default=0, ge=0)
    valid_until: datetime | None = None


class PromoBadgeRead(BaseModel):
    code: str
    kind: str
    title: str
    description: str
    icon: str | None = None
    is_active: bool
    priority: int
    valid_until: datetime | None = None

    @classmethod
    def from_obj(cls, obj: dict | BaseModel, locale: str) -> "PromoBadgeRead":
        if isinstance(obj, dict):
            return cls(
                code=obj.get("code", ""),
                kind=obj.get("kind", "info"),
                title=pick_locale(obj.get("title", {}) or {}, locale),
                description=pick_locale(obj.get("description", {}) or {}, locale),
                icon=obj.get("icon"),
                is_active=obj.get("is_active", True),
                priority=obj.get("priority", 0),
                valid_until=obj.get("valid_until"),
            )
        return cls(
            code=getattr(obj, "code", ""),
            kind=getattr(obj, "kind", "info"),
            title=pick_locale(getattr(obj, "title", {}) or {}, locale),
            description=pick_locale(getattr(obj, "description", {}) or {}, locale),
            icon=getattr(obj, "icon", None),
            is_active=getattr(obj, "is_active", True),
            priority=getattr(obj, "priority", 0),
            valid_until=getattr(obj, "valid_until", None),
        )


class RatingBreakdown(BaseModel):
    cleanliness: Decimal | None = None
    amenities: Decimal | None = None
    location: Decimal | None = None
    service: Decimal | None = None
    treatment: Decimal | None = None
    value: Decimal | None = None
    food: Decimal | None = None


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
    policies: SanatoriumPolicies | None = None

    @field_validator("agent_discount_tiers")
    @classmethod
    def _validate_tiers(
        cls, value: list[AgentDiscountTier] | None
    ) -> list[AgentDiscountTier] | None:
        if value is None:
            return None
        return _normalize_tiers(value)


class _SanatoriumReadCommon(BaseModel):
    """Shared non-i18n fields between public and admin sanatorium reads."""

    id: uuid.UUID
    slug: str
    city: str
    region_id: uuid.UUID | None
    destination_id: uuid.UUID | None
    lat: Decimal | None
    lng: Decimal | None
    phones: list[str]
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
    """Public read: i18n fields resolved to a single locale string."""

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
            id=obj.id,
            slug=obj.slug,
            name=pick_locale(obj.name, locale),
            description=pick_locale(obj.description, locale),
            city=obj.city,
            region_id=obj.region_id,
            region=(RegionRead.from_obj(obj.region, locale) if obj.region else None),
            destination_id=obj.destination_id,
            destination=(
                DestinationRead.from_obj(obj.destination, locale)
                if obj.destination
                else None
            ),
            address=pick_locale(obj.address, locale),
            lat=obj.lat,
            lng=obj.lng,
            phones=obj.phones,
            website=obj.website,
            check_in_time=obj.check_in_time,
            check_out_time=obj.check_out_time,
            pets_allowed=obj.pets_allowed,
            service_animals_allowed=obj.service_animals_allowed,
            min_checkin_age=obj.min_checkin_age,
            quiet_hours_from=obj.quiet_hours_from,
            quiet_hours_to=obj.quiet_hours_to,
            payment_methods=obj.payment_methods,
            house_rules=pick_locale(obj.house_rules, locale),
            cancellation_policy=pick_locale(obj.cancellation_policy, locale),
            weekly_schedule=obj.weekly_schedule,
            stars=obj.stars,
            status=obj.status,
            property_type=obj.property_type,
            wellness_category=obj.wellness_category,
            treatment_focuses=obj.treatment_focuses,
            treatment_profile=TreatmentProfileRead.from_obj(
                obj.treatment_profile, locale
            ),
            year_opened=obj.year_opened,
            languages_spoken=obj.languages_spoken,
            highlights=obj.highlights,
            is_featured=obj.is_featured,
            display_order=obj.display_order,
            promo_badges=[
                PromoBadgeRead.from_obj(badge, locale)
                for badge in (obj.promo_badges or [])
                if (badge.get("is_active", True) if isinstance(badge, dict) else True)
            ],
            surroundings=obj.surroundings,
            venues=obj.venues,
            meal_schedule=obj.meal_schedule,
            service_matrix=ServiceMatrixRead.from_obj(obj.service_matrix, locale),
            avg_rating=obj.avg_rating,
            review_count=obj.review_count,
            rating_breakdown=RatingBreakdown(**(obj.rating_breakdown or {})),
            admin_user_id=obj.admin_user_id,
            platform_commission_percent=obj.platform_commission_percent,
            b2b_commission_percent=obj.b2b_commission_percent,
            agent_discount_tiers=[
                AgentDiscountTier(**t) for t in (obj.agent_discount_tiers or [])
            ],
            created_at=obj.created_at,
            updated_at=obj.updated_at,
            images=[SanatoriumImageRead.model_validate(i) for i in obj.images],
            amenities=[
                SanatoriumAmenityRead.from_obj(link, locale)
                for link in obj.amenity_links
            ],
            medical_base=MedicalBaseRead.from_obj(obj.medical_base, locale),
            policies=SanatoriumPolicies.model_validate(obj.policies or {}),
        )


class SanatoriumAdminRead(_SanatoriumReadCommon):
    """Admin read: i18n fields returned as {uz, ru, en} dicts."""

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


class SanatoriumList(BaseModel):
    items: list[SanatoriumRead]
    total: int
    limit: int
    offset: int


class SanatoriumAdminList(BaseModel):
    items: list[SanatoriumAdminRead]
    total: int
    limit: int
    offset: int


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
