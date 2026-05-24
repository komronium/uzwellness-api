import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.utils import pick_locale
from app.models.room import RoomView
from app.schemas.amenity import AmenityAdminRead, AmenityRead
from app.schemas.common import Translations, TranslationsCreate

BedType = Literal["single", "double", "twin", "queen", "king", "sofa_bed", "bunk"]


class BedConfig(BaseModel):
    type: BedType
    count: int = Field(default=1, ge=1)
    size_cm: str | None = Field(default=None, max_length=20)


class BeddingOption(BaseModel):
    """One way to make up the room. Beds within an option coexist (king + sofa);
    multiple options are alternatives the guest picks between (2 single OR 1 double).
    """

    beds: list[BedConfig] = Field(min_length=1)
    label: str | None = Field(default=None, max_length=120)


class RoomImageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    url: str
    order: int
    is_primary: bool
    is_video: bool
    caption: str | None
    created_at: datetime


class RoomImageUpdate(BaseModel):
    is_primary: bool | None = None
    order: int | None = Field(default=None, ge=0)
    caption: str | None = Field(default=None, max_length=255)


class RoomCreate(BaseModel):
    sanatorium_id: uuid.UUID
    name: TranslationsCreate
    description: Translations = Field(default_factory=Translations)
    amenity_ids: list[uuid.UUID] = Field(default_factory=list)
    size_sqm: int | None = Field(default=None, ge=0)
    floor: str | None = Field(default=None, max_length=20)
    beds: list[BeddingOption] = Field(default_factory=list)
    view: RoomView | None = None
    smoking_allowed: bool = False
    capacity: int = Field(ge=1)
    max_adults: int | None = Field(default=None, ge=0)
    max_children: int | None = Field(default=None, ge=0)
    inventory_count: int = Field(default=1, ge=1)
    base_price: Decimal = Field(ge=0, decimal_places=2)
    base_price_weekend: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    base_currency: str = Field(pattern=r"^(UZS|USD)$")
    min_nights: int = Field(default=1, ge=1)


class RoomUpdate(BaseModel):
    name: Translations | None = None
    description: Translations | None = None
    amenity_ids: list[uuid.UUID] | None = None
    size_sqm: int | None = Field(default=None, ge=0)
    floor: str | None = Field(default=None, max_length=20)
    beds: list[BeddingOption] | None = None
    view: RoomView | None = None
    smoking_allowed: bool | None = None
    capacity: int | None = Field(default=None, ge=1)
    max_adults: int | None = Field(default=None, ge=0)
    max_children: int | None = Field(default=None, ge=0)
    inventory_count: int | None = Field(default=None, ge=0)
    base_price: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    base_price_weekend: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    base_currency: str | None = Field(default=None, pattern=r"^(UZS|USD)$")
    markup_percent: Decimal | None = Field(default=None, ge=0, le=100, decimal_places=2)
    discount_percent: Decimal | None = Field(default=None, ge=0, le=100, decimal_places=2)
    min_nights: int | None = Field(default=None, ge=1)
    is_active: bool | None = None


class _RoomReadCommon(BaseModel):
    """Shared fields between public and admin Room reads (excluding i18n)."""

    id: uuid.UUID
    sanatorium_id: uuid.UUID
    size_sqm: int | None = None
    floor: str | None = None
    beds: list[BeddingOption] = Field(default_factory=list)
    view: RoomView | None = None
    smoking_allowed: bool = False
    capacity: int
    max_adults: int | None = None
    max_children: int | None = None
    inventory_count: int
    images: list[RoomImageRead] = Field(default_factory=list)
    base_price: Decimal
    base_price_weekend: Decimal | None = None
    base_currency: str
    markup_percent: Decimal
    discount_percent: Decimal | None = None
    min_nights: int
    is_active: bool
    has_availability: bool = False
    final_price: Decimal = Decimal("0")
    final_price_uzs: Decimal | None = None
    final_price_usd: Decimal | None = None
    final_price_weekend: Decimal | None = None
    final_price_weekend_uzs: Decimal | None = None
    final_price_weekend_usd: Decimal | None = None
    created_at: datetime
    updated_at: datetime


class RoomRead(_RoomReadCommon):
    """Public read: i18n fields resolved to a single locale string."""

    name: str
    description: str
    amenities: list[AmenityRead] = Field(default_factory=list)

    @classmethod
    def from_obj(cls, obj, locale: str) -> "RoomRead":
        return cls(
            id=obj.id,
            sanatorium_id=obj.sanatorium_id,
            name=pick_locale(obj.name, locale),
            description=pick_locale(obj.description, locale),
            amenities=[AmenityRead.from_obj(a, locale) for a in obj.amenities],
            size_sqm=obj.size_sqm,
            floor=obj.floor,
            beds=obj.beds or [],
            view=obj.view,
            smoking_allowed=obj.smoking_allowed,
            capacity=obj.capacity,
            max_adults=obj.max_adults,
            max_children=obj.max_children,
            inventory_count=obj.inventory_count,
            images=[RoomImageRead.model_validate(i) for i in obj.images],
            base_price=obj.base_price,
            base_price_weekend=obj.base_price_weekend,
            base_currency=obj.base_currency,
            markup_percent=obj.markup_percent,
            discount_percent=obj.discount_percent,
            min_nights=obj.min_nights,
            is_active=obj.is_active,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )


class RoomAdminRead(_RoomReadCommon):
    """Admin read: i18n fields returned as {uz, ru, en} dicts."""

    model_config = ConfigDict(from_attributes=True)

    name: dict
    description: dict
    amenities: list[AmenityAdminRead] = Field(default_factory=list)


class RoomList(BaseModel):
    items: list[RoomRead]
    total: int
    limit: int
    offset: int


class RoomAdminList(BaseModel):
    items: list[RoomAdminRead]
    total: int
    limit: int
    offset: int


class RoomSearchResult(RoomRead):
    """Search result row: includes availability flags for a date range."""

    available: bool
    rooms_count_needed: int
    unavailable_reason: str | None = None


class AvailabilityBlock(BaseModel):
    """Block (close) units across a date range — e.g. for maintenance.

    `date_to` is exclusive (matches booking semantics).
    """

    date_from: date
    date_to: date
    units_blocked: int = Field(ge=0, description="Units to mark blocked per day")


class AvailabilityUpsert(BaseModel):
    units_blocked: int = Field(ge=0)


class AvailabilityRead(BaseModel):
    """Per-day availability row (computed view).

    `units_available = inventory_count - units_blocked - units_booked`.
    """

    date: date
    inventory_count: int
    units_blocked: int
    units_booked: int
    units_available: int


class RoomPricePeriodCreate(BaseModel):
    label: str | None = Field(default=None, max_length=120)
    date_from: date
    date_to: date
    base_price: Decimal = Field(ge=0, decimal_places=2)
    base_price_weekend: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    discount_percent: Decimal | None = Field(default=None, ge=0, le=100, decimal_places=2)


class RoomPricePeriodUpdate(BaseModel):
    label: str | None = Field(default=None, max_length=120)
    date_from: date | None = None
    date_to: date | None = None
    base_price: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    base_price_weekend: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    discount_percent: Decimal | None = Field(default=None, ge=0, le=100, decimal_places=2)


class RoomPricePeriodRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    room_id: uuid.UUID
    label: str | None
    date_from: date
    date_to: date
    base_price: Decimal
    base_price_weekend: Decimal | None
    discount_percent: Decimal | None
    created_at: datetime
