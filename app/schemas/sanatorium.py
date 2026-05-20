import uuid
from datetime import datetime, time
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.sanatorium import PropertyType, SanatoriumStatus, WellnessCategory
from app.schemas.amenity import AmenityRead
from app.schemas.common import Translations


class AgentDiscountTier(BaseModel):
    min_bookings: int = Field(ge=1, le=10000)
    discount_percent: Decimal = Field(ge=0, le=100)

TREATMENT_FOCUS_VALUES = frozenset({
    "cardiovascular", "digestive", "musculoskeletal",
    "respiratory", "neurological", "dermatology",
    "endocrine", "wellness",
})

PAYMENT_METHOD_VALUES = frozenset({
    "cash", "bank_transfer",
    "uzcard", "visa", "mastercard", "jcb", "unionpay", "mir",
})


class SanatoriumImageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    url: str
    order: int
    is_primary: bool
    caption: str | None
    created_at: datetime


class SanatoriumImageUpdate(BaseModel):
    is_primary: bool | None = None
    order: int | None = Field(default=None, ge=0)
    caption: str | None = Field(default=None, max_length=255)


class SanatoriumBase(BaseModel):
    name: Translations = Field(default_factory=Translations)
    description: Translations = Field(default_factory=Translations)
    city: str = Field(min_length=1, max_length=120)
    region: str | None = Field(default=None, max_length=120)
    address: Translations = Field(default_factory=Translations)
    lat: Decimal | None = Field(default=None, ge=-90, le=90)
    lng: Decimal | None = Field(default=None, ge=-180, le=180)
    phones: list[str] = Field(default_factory=list, max_length=10)
    website: str | None = Field(default=None, max_length=255)
    check_in_time: time | None = None
    check_out_time: time | None = None
    payment_methods: list[str] = Field(default_factory=list)
    house_rules: Translations = Field(default_factory=Translations)
    cancellation_policy: Translations = Field(default_factory=Translations)
    weekly_schedule: dict = Field(default_factory=dict)
    stars: int = Field(ge=1, le=5)
    property_type: PropertyType = PropertyType.SANATORIUM
    wellness_category: WellnessCategory | None = None
    treatment_focuses: list[str] = Field(default_factory=list)


class SanatoriumCreate(SanatoriumBase):
    slug: str | None = Field(default=None, max_length=255)
    admin_user_id: uuid.UUID | None = None
    amenity_ids: list[uuid.UUID] = Field(default_factory=list)
    platform_commission_percent: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    b2b_commission_percent: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    agent_discount_tiers: list[AgentDiscountTier] = Field(default_factory=list)

    @field_validator("agent_discount_tiers")
    @classmethod
    def _validate_tiers(
        cls, value: list[AgentDiscountTier]
    ) -> list[AgentDiscountTier]:
        return _normalize_tiers(value)


class SanatoriumUpdate(BaseModel):
    name: Translations | None = None
    slug: str | None = Field(default=None, max_length=255)
    description: Translations | None = None
    city: str | None = Field(default=None, min_length=1, max_length=120)
    region: str | None = Field(default=None, max_length=120)
    address: Translations | None = None
    lat: Decimal | None = Field(default=None, ge=-90, le=90)
    lng: Decimal | None = Field(default=None, ge=-180, le=180)
    phones: list[str] | None = Field(default=None, max_length=10)
    website: str | None = Field(default=None, max_length=255)
    check_in_time: time | None = None
    check_out_time: time | None = None
    payment_methods: list[str] | None = None
    house_rules: Translations | None = None
    cancellation_policy: Translations | None = None
    weekly_schedule: dict | None = None
    stars: int | None = Field(default=None, ge=1, le=5)
    property_type: PropertyType | None = None
    wellness_category: WellnessCategory | None = None
    admin_user_id: uuid.UUID | None = None
    treatment_focuses: list[str] | None = None
    amenity_ids: list[uuid.UUID] | None = None
    platform_commission_percent: Decimal | None = Field(default=None, ge=0, le=100)
    b2b_commission_percent: Decimal | None = Field(default=None, ge=0, le=100)
    agent_discount_tiers: list[AgentDiscountTier] | None = None

    @field_validator("agent_discount_tiers")
    @classmethod
    def _validate_tiers(
        cls, value: list[AgentDiscountTier] | None
    ) -> list[AgentDiscountTier] | None:
        if value is None:
            return None
        return _normalize_tiers(value)


class SanatoriumRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: Translations
    slug: str
    description: Translations
    city: str
    region: str | None
    address: Translations
    lat: Decimal | None
    lng: Decimal | None
    phones: list[str]
    website: str | None
    check_in_time: time | None
    check_out_time: time | None
    payment_methods: list[str]
    house_rules: Translations
    cancellation_policy: Translations
    weekly_schedule: dict
    stars: int
    status: SanatoriumStatus
    property_type: PropertyType
    wellness_category: WellnessCategory | None
    treatment_focuses: list[str]
    avg_rating: Decimal | None
    review_count: int
    admin_user_id: uuid.UUID | None
    platform_commission_percent: Decimal
    b2b_commission_percent: Decimal
    agent_discount_tiers: list[AgentDiscountTier] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    images: list[SanatoriumImageRead] = Field(default_factory=list)
    amenities: list[AmenityRead] = Field(default_factory=list)


class SanatoriumList(BaseModel):
    items: list[SanatoriumRead]
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
