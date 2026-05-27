import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.utils import pick_locale
from app.models.room import RoomView
from app.schemas.amenity import AmenityAdminRead, AmenityRead
from app.schemas.common import Translations, TranslationsCreate

BedType = Literal["single", "double", "twin", "queen", "king", "sofa_bed", "bunk"]


def normalize_floor(value) -> str | None:
    """Store floor values in one display-safe format.

    Valid examples:
    - "2"
    - "2-4" for a continuous range
    - "2,4" for discrete floors
    """
    if value is None:
        return None
    if isinstance(value, int):
        value = str(value)
    if not isinstance(value, str):
        raise ValueError("floor must be a string or integer")

    floor = value.strip()
    if not floor:
        return None
    if "/" in floor:
        raise ValueError("use '2-4' for ranges or '2,4' for separate floors")

    if floor.isdigit():
        return floor

    if "-" in floor:
        parts = [part.strip() for part in floor.split("-")]
        if len(parts) != 2 or not all(part.isdigit() for part in parts):
            raise ValueError("floor range must look like '2-4'")
        start, end = (int(part) for part in parts)
        if start > end:
            raise ValueError("floor range start must be less than or equal to end")
        return f"{start}-{end}"

    if "," in floor:
        parts = [part.strip() for part in floor.split(",")]
        if not parts or not all(part.isdigit() for part in parts):
            raise ValueError("floor list must look like '2,4'")
        return ",".join(parts)

    raise ValueError("floor must look like '2', '2-4', or '2,4'")


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


class RoomBathroomFeatures(BaseModel):
    private: bool | None = None
    type: Literal["shower", "bathtub", "shower_and_bathtub"] | None = None
    bidet: bool | None = None
    toiletries: bool | None = None
    hairdryer: bool | None = None
    bathrobe: bool | None = None
    slippers: bool | None = None


class RoomClimateFeatures(BaseModel):
    air_conditioning: bool | None = None
    heating: bool | None = None


class RoomKitchenFeatures(BaseModel):
    refrigerator: bool | None = None
    minibar: bool | None = None
    kettle: bool | None = None
    kitchenette: bool | None = None


class RoomAccessibilityFeatures(BaseModel):
    wheelchair_accessible: bool | None = None
    roll_in_shower: bool | None = None
    grab_bars: bool | None = None
    visual_alarm: bool | None = None


class RoomSafetyFeatures(BaseModel):
    safe: bool | None = None
    smoke_detector: bool | None = None
    smart_lock: bool | None = None


class RoomEntertainmentFeatures(BaseModel):
    tv: bool | None = None
    smart_tv: bool | None = None
    satellite_channels: bool | None = None


class RoomComfortFeatures(BaseModel):
    balcony: bool | None = None
    terrace: bool | None = None
    desk: bool | None = None
    sofa: bool | None = None
    carpet: bool | None = None


class RoomFeatures(BaseModel):
    has_window: bool | None = None
    bathroom: RoomBathroomFeatures = Field(default_factory=RoomBathroomFeatures)
    climate: RoomClimateFeatures = Field(default_factory=RoomClimateFeatures)
    kitchen: RoomKitchenFeatures = Field(default_factory=RoomKitchenFeatures)
    accessibility: RoomAccessibilityFeatures = Field(
        default_factory=RoomAccessibilityFeatures
    )
    safety: RoomSafetyFeatures = Field(default_factory=RoomSafetyFeatures)
    entertainment: RoomEntertainmentFeatures = Field(
        default_factory=RoomEntertainmentFeatures
    )
    comfort: RoomComfortFeatures = Field(default_factory=RoomComfortFeatures)
    highlights: list[str] = Field(default_factory=list)


class RoomImageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    url: str
    order: int
    is_primary: bool
    is_video: bool
    is_360: bool
    category: str | None
    caption: str | None
    caption_i18n: dict
    alt_text: dict
    tags: list[str]
    created_at: datetime


class RoomImageUpdate(BaseModel):
    is_primary: bool | None = None
    is_video: bool | None = None
    is_360: bool | None = None
    category: str | None = Field(default=None, max_length=40)
    order: int | None = Field(default=None, ge=0)
    caption: str | None = Field(default=None, max_length=255)
    caption_i18n: Translations | None = None
    alt_text: Translations | None = None
    tags: list[str] | None = None


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
    room_features: RoomFeatures = Field(default_factory=RoomFeatures)
    capacity: int = Field(ge=1)
    max_adults: int | None = Field(default=None, ge=0)
    max_children: int | None = Field(default=None, ge=0)
    inventory_count: int = Field(default=1, ge=1)
    base_price: Decimal = Field(ge=0, decimal_places=2)
    base_price_weekend: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    base_currency: str = Field(pattern=r"^(UZS|USD)$")
    min_nights: int = Field(default=1, ge=1)

    @field_validator("floor", mode="before")
    @classmethod
    def _normalize_floor(cls, value):
        return normalize_floor(value)


class RoomUpdate(BaseModel):
    name: Translations | None = None
    description: Translations | None = None
    amenity_ids: list[uuid.UUID] | None = None
    size_sqm: int | None = Field(default=None, ge=0)
    floor: str | None = Field(default=None, max_length=20)
    beds: list[BeddingOption] | None = None
    view: RoomView | None = None
    smoking_allowed: bool | None = None
    room_features: RoomFeatures | None = None
    capacity: int | None = Field(default=None, ge=1)
    max_adults: int | None = Field(default=None, ge=0)
    max_children: int | None = Field(default=None, ge=0)
    inventory_count: int | None = Field(default=None, ge=0)
    base_price: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    base_price_weekend: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    base_currency: str | None = Field(default=None, pattern=r"^(UZS|USD)$")
    markup_percent: Decimal | None = Field(default=None, ge=0, le=100, decimal_places=2)
    discount_percent: Decimal | None = Field(
        default=None, ge=0, le=100, decimal_places=2
    )
    min_nights: int | None = Field(default=None, ge=1)
    is_active: bool | None = None

    @field_validator("floor", mode="before")
    @classmethod
    def _normalize_floor(cls, value):
        return normalize_floor(value)


class _RoomReadCommon(BaseModel):
    """Shared fields between public and admin Room reads (excluding i18n)."""

    id: uuid.UUID
    sanatorium_id: uuid.UUID
    size_sqm: int | None = None
    floor: str | None = None
    beds: list[BeddingOption] = Field(default_factory=list)
    view: RoomView | None = None
    smoking_allowed: bool = False
    room_features: RoomFeatures = Field(default_factory=RoomFeatures)
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
            room_features=RoomFeatures.model_validate(obj.room_features or {}),
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
    discount_percent: Decimal | None = Field(
        default=None, ge=0, le=100, decimal_places=2
    )


class RoomPricePeriodUpdate(BaseModel):
    label: str | None = Field(default=None, max_length=120)
    date_from: date | None = None
    date_to: date | None = None
    base_price: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    base_price_weekend: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    discount_percent: Decimal | None = Field(
        default=None, ge=0, le=100, decimal_places=2
    )


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
