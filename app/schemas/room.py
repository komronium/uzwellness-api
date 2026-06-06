import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.utils import pick_locale
from app.models.amenity import AmenityCost, AmenitySelectionStatus
from app.models.room import (
    AccommodationType,
    GenderRestriction,
    RoomSizePolicy,
    RoomView,
    SmokingPolicy,
    WindowPolicy,
)
from app.schemas.amenity import AmenityAdminRead, AmenityRead
from app.schemas.common import Translations, TranslationsCreate
from app.schemas.room_availability import (
    AvailabilityBlock,
    AvailabilityRead,
    AvailabilityUpsert,
)
from app.schemas.room_image import RoomImageRead, RoomImageUpdate

BedType = Literal["single", "double", "twin", "queen", "king", "sofa_bed", "bunk"]

__all__ = (
    "AvailabilityBlock",
    "AvailabilityRead",
    "AvailabilityUpsert",
    "RoomImageRead",
    "RoomImageUpdate",
)


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


def normalize_bedding_options(value):
    if value is None or not isinstance(value, list):
        return value
    if not value:
        return value
    if all(_is_legacy_bed_config(item) for item in value):
        return [{"beds": [_normalize_legacy_bed_config(item) for item in value]}]
    return [
        {"beds": [_normalize_legacy_bed_config(item)]}
        if _is_legacy_bed_config(item)
        else item
        for item in value
    ]


def _is_legacy_bed_config(value) -> bool:
    return isinstance(value, dict) and "type" in value and "beds" not in value


def _normalize_legacy_bed_config(value: dict) -> dict:
    data = dict(value)
    width_cm = data.pop("width_cm", None)
    if "size_cm" not in data and width_cm is not None:
        data["size_cm"] = str(width_cm)
    return data


class BedConfig(BaseModel):
    type: BedType
    count: int = Field(default=1, ge=1)
    size_cm: str | None = Field(default=None, max_length=20)

    @model_validator(mode="before")
    @classmethod
    def _normalize_legacy_shape(cls, value):
        if not isinstance(value, dict):
            return value
        return _normalize_legacy_bed_config(value)


class BeddingOption(BaseModel):
    """One way to make up the room. Beds within an option coexist (king + sofa);
    multiple options are alternatives the guest picks between (2 single OR 1 double).
    """

    beds: list[BedConfig] = Field(min_length=1)
    label: str | None = Field(default=None, max_length=120)

    @model_validator(mode="before")
    @classmethod
    def _normalize_legacy_shape(cls, value):
        if _is_legacy_bed_config(value):
            return {"beds": [_normalize_legacy_bed_config(value)]}
        return value


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

    @model_validator(mode="before")
    @classmethod
    def _normalize_legacy_shape(cls, value):
        if isinstance(value, BaseModel) or not isinstance(value, dict):
            return value

        data = dict(value)
        bathroom = data.get("bathroom")
        if isinstance(bathroom, str):
            bathroom_value = bathroom.strip().lower()
            if bathroom_value in {"private", "private_bathroom", "ensuite"}:
                data["bathroom"] = {"private": True}
            elif bathroom_value in {"shared", "shared_bathroom"}:
                data["bathroom"] = {"private": False}

        windows = data.pop("windows", None)
        if "has_window" not in data and windows is not None:
            if isinstance(windows, bool):
                data["has_window"] = windows
            elif isinstance(windows, str):
                windows_value = windows.strip().lower()
                if windows_value in {"all", "some", "yes", "true", "1"}:
                    data["has_window"] = True
                elif windows_value in {"none", "no", "false", "0"}:
                    data["has_window"] = False

        if "balcony" in data:
            comfort = data.get("comfort")
            if not isinstance(comfort, dict):
                comfort = {}
            comfort.setdefault("balcony", data.pop("balcony"))
            data["comfort"] = comfort

        return data


class RoomAmenityItem(BaseModel):
    amenity_id: uuid.UUID
    status: AmenitySelectionStatus = AmenitySelectionStatus.YES
    cost: AmenityCost = AmenityCost.FREE
    is_available: bool = True
    details: dict = Field(default_factory=dict)
    display_order: int = Field(default=0, ge=0)


class RoomAmenityRead(BaseModel):
    status: AmenitySelectionStatus
    cost: AmenityCost
    is_available: bool
    details: dict
    display_order: int
    amenity: AmenityRead

    @classmethod
    def from_obj(cls, link, locale: str) -> "RoomAmenityRead":
        return cls(
            status=link.status,
            cost=link.cost,
            is_available=link.is_available,
            details=link.details or {},
            display_order=link.display_order,
            amenity=AmenityRead.from_obj(link.amenity, locale),
        )


class RoomAmenityAdminRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: AmenitySelectionStatus
    cost: AmenityCost
    is_available: bool
    details: dict
    display_order: int
    amenity: AmenityAdminRead


class RoomCreate(BaseModel):
    sanatorium_id: uuid.UUID
    name: TranslationsCreate
    description: Translations = Field(default_factory=Translations)
    amenity_ids: list[uuid.UUID] = Field(default_factory=list)
    amenity_items: list[RoomAmenityItem] = Field(default_factory=list)
    size_sqm: int | None = Field(default=None, ge=0)
    room_size_policy: RoomSizePolicy = RoomSizePolicy.SAME_SIZE
    floor: str | None = Field(default=None, max_length=20)
    beds: list[BeddingOption] = Field(default_factory=list)
    view: RoomView | None = None
    smoking_allowed: bool = False
    smoking_policy: SmokingPolicy | None = None
    window_policy: WindowPolicy | None = None
    window_description: str | None = Field(default=None, max_length=255)
    room_features: RoomFeatures = Field(default_factory=RoomFeatures)
    accommodation_type: AccommodationType = AccommodationType.HOTEL_ROOM
    gender_restriction: GenderRestriction | None = None
    capacity: int = Field(ge=1)
    max_adults: int | None = Field(default=None, ge=0)
    max_children: int | None = Field(default=None, ge=0)
    max_child_rate_children: int | None = Field(default=None, ge=0)
    inventory_count: int = Field(default=1, ge=1)
    room_advisories: list[str] = Field(default_factory=list)
    base_price: Decimal = Field(ge=0, decimal_places=2)
    base_price_weekend: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    base_currency: str = Field(pattern=r"^(UZS|USD)$")
    min_nights: int = Field(default=1, ge=1)
    display_order: int = Field(default=0, ge=0)

    @field_validator("floor", mode="before")
    @classmethod
    def _normalize_floor(cls, value):
        return normalize_floor(value)

    @field_validator("beds", mode="before")
    @classmethod
    def _normalize_beds(cls, value):
        return normalize_bedding_options(value)


class RoomUpdate(BaseModel):
    name: Translations | None = None
    description: Translations | None = None
    amenity_ids: list[uuid.UUID] | None = None
    amenity_items: list[RoomAmenityItem] | None = None
    size_sqm: int | None = Field(default=None, ge=0)
    room_size_policy: RoomSizePolicy | None = None
    floor: str | None = Field(default=None, max_length=20)
    beds: list[BeddingOption] | None = None
    view: RoomView | None = None
    smoking_allowed: bool | None = None
    smoking_policy: SmokingPolicy | None = None
    window_policy: WindowPolicy | None = None
    window_description: str | None = Field(default=None, max_length=255)
    room_features: RoomFeatures | None = None
    accommodation_type: AccommodationType | None = None
    gender_restriction: GenderRestriction | None = None
    capacity: int | None = Field(default=None, ge=1)
    max_adults: int | None = Field(default=None, ge=0)
    max_children: int | None = Field(default=None, ge=0)
    max_child_rate_children: int | None = Field(default=None, ge=0)
    inventory_count: int | None = Field(default=None, ge=0)
    room_advisories: list[str] | None = None
    base_price: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    base_price_weekend: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    base_currency: str | None = Field(default=None, pattern=r"^(UZS|USD)$")
    markup_percent: Decimal | None = Field(default=None, ge=0, le=100, decimal_places=2)
    discount_percent: Decimal | None = Field(
        default=None, ge=0, le=100, decimal_places=2
    )
    min_nights: int | None = Field(default=None, ge=1)
    is_active: bool | None = None
    display_order: int | None = Field(default=None, ge=0)

    @field_validator("floor", mode="before")
    @classmethod
    def _normalize_floor(cls, value):
        return normalize_floor(value)

    @field_validator("beds", mode="before")
    @classmethod
    def _normalize_beds(cls, value):
        return normalize_bedding_options(value)


class _RoomReadCommon(BaseModel):
    """Shared fields between public and admin Room reads (excluding i18n)."""

    id: uuid.UUID
    sanatorium_id: uuid.UUID
    size_sqm: int | None = None
    room_size_policy: RoomSizePolicy = RoomSizePolicy.SAME_SIZE
    floor: str | None = None
    beds: list[BeddingOption] = Field(default_factory=list)
    view: RoomView | None = None
    smoking_allowed: bool = False
    smoking_policy: SmokingPolicy = SmokingPolicy.NON_SMOKING
    window_policy: WindowPolicy | None = None
    window_description: str | None = None
    room_features: RoomFeatures = Field(default_factory=RoomFeatures)
    accommodation_type: AccommodationType = AccommodationType.HOTEL_ROOM
    gender_restriction: GenderRestriction | None = None
    capacity: int
    max_adults: int | None = None
    max_children: int | None = None
    max_child_rate_children: int | None = None
    inventory_count: int
    room_advisories: list[str] = Field(default_factory=list)
    images: list[RoomImageRead] = Field(default_factory=list)
    base_price: Decimal
    base_price_weekend: Decimal | None = None
    base_currency: str
    markup_percent: Decimal
    discount_percent: Decimal | None = None
    min_nights: int
    is_active: bool
    display_order: int
    deleted_at: datetime | None = None
    has_availability: bool = False
    final_price: Decimal = Decimal("0")
    final_price_uzs: Decimal | None = None
    final_price_usd: Decimal | None = None
    final_price_weekend: Decimal | None = None
    final_price_weekend_uzs: Decimal | None = None
    final_price_weekend_usd: Decimal | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("beds", mode="before")
    @classmethod
    def _normalize_beds(cls, value):
        return normalize_bedding_options(value)


class RoomRead(_RoomReadCommon):
    """Public read: i18n fields resolved to a single locale string."""

    name: str
    description: str
    amenities: list[AmenityRead] = Field(default_factory=list)
    amenity_items: list["RoomAmenityRead"] = Field(default_factory=list)

    @classmethod
    def from_obj(cls, obj, locale: str) -> "RoomRead":
        return cls(
            id=obj.id,
            sanatorium_id=obj.sanatorium_id,
            name=pick_locale(obj.name, locale),
            description=pick_locale(obj.description, locale),
            amenities=[AmenityRead.from_obj(a, locale) for a in obj.amenities],
            amenity_items=[
                RoomAmenityRead.from_obj(link, locale) for link in obj.amenity_links
            ],
            size_sqm=obj.size_sqm,
            room_size_policy=obj.room_size_policy,
            floor=obj.floor,
            beds=obj.beds or [],
            view=obj.view,
            smoking_allowed=obj.smoking_allowed,
            smoking_policy=obj.smoking_policy,
            window_policy=obj.window_policy,
            window_description=obj.window_description,
            room_features=RoomFeatures.model_validate(obj.room_features or {}),
            accommodation_type=obj.accommodation_type,
            gender_restriction=obj.gender_restriction,
            capacity=obj.capacity,
            max_adults=obj.max_adults,
            max_children=obj.max_children,
            max_child_rate_children=obj.max_child_rate_children,
            inventory_count=obj.inventory_count,
            room_advisories=obj.room_advisories or [],
            images=[RoomImageRead.model_validate(i) for i in obj.images],
            base_price=obj.base_price,
            base_price_weekend=obj.base_price_weekend,
            base_currency=obj.base_currency,
            markup_percent=obj.markup_percent,
            discount_percent=obj.discount_percent,
            min_nights=obj.min_nights,
            is_active=obj.is_active,
            display_order=obj.display_order,
            deleted_at=obj.deleted_at,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )


class RoomAdminRead(_RoomReadCommon):
    """Admin read: i18n fields returned as {uz, ru, en} dicts."""

    model_config = ConfigDict(from_attributes=True)

    name: dict
    description: dict
    amenities: list[AmenityAdminRead] = Field(default_factory=list)
    amenity_items: list["RoomAmenityAdminRead"] = Field(
        default_factory=list, validation_alias="amenity_links"
    )


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


class RoomOrderItem(BaseModel):
    room_id: uuid.UUID
    display_order: int = Field(ge=0)


class RoomOrderUpdate(BaseModel):
    sanatorium_id: uuid.UUID
    items: list[RoomOrderItem] = Field(min_length=1)


class RoomSearchResult(RoomRead):
    """Search result row: includes availability flags for a date range."""

    available: bool
    rooms_count_needed: int
    unavailable_reason: str | None = None


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
