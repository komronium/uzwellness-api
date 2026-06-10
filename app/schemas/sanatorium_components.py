import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.utils import pick_locale
from app.models.amenity import AmenityCost, AmenitySelectionStatus
from app.schemas.amenity import AmenityAdminRead, AmenityRead
from app.schemas.common import Translations


class SanatoriumAmenityItem(BaseModel):
    amenity_id: uuid.UUID
    cost: AmenityCost = AmenityCost.FREE
    is_available: bool = True
    status: AmenitySelectionStatus = AmenitySelectionStatus.YES
    details: dict = Field(default_factory=dict)
    display_order: int = Field(default=0, ge=0)


class SanatoriumAmenityRead(BaseModel):
    cost: AmenityCost
    is_available: bool
    status: AmenitySelectionStatus
    details: dict
    display_order: int
    amenity: AmenityRead

    @classmethod
    def from_obj(cls, link, locale: str) -> "SanatoriumAmenityRead":
        return cls(
            cost=link.cost,
            is_available=link.is_available,
            status=link.status,
            details=link.details or {},
            display_order=link.display_order,
            amenity=AmenityRead.from_obj(link.amenity, locale),
        )


class SanatoriumAmenityAdminRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    cost: AmenityCost
    is_available: bool
    status: AmenitySelectionStatus
    details: dict
    display_order: int
    amenity: AmenityAdminRead


def _validate_i18n_name(value: str | dict, max_length: int) -> str | dict:
    """Names arrive either as a plain string (legacy) or a {uz,ru,en} dict."""
    if isinstance(value, str):
        if not value.strip():
            raise ValueError("name must not be empty")
        if len(value) > max_length:
            raise ValueError(f"name must be at most {max_length} characters")
        return value
    translations = {
        key: text
        for key, text in value.items()
        if isinstance(text, str) and text.strip()
    }
    if not translations:
        raise ValueError("name must contain at least one non-empty translation")
    for text in translations.values():
        if len(text) > max_length:
            raise ValueError(f"name must be at most {max_length} characters")
    return value


class Surrounding(BaseModel):
    name: str | dict
    type: str = Field(min_length=1, max_length=40)
    distance_m: int = Field(ge=0)

    @field_validator("name")
    @classmethod
    def _check_name(cls, value: str | dict) -> str | dict:
        return _validate_i18n_name(value, 200)


class Venue(BaseModel):
    name: str | dict
    type: str = Field(min_length=1, max_length=40)
    building: str | None = Field(default=None, max_length=120)
    hours: str | None = Field(default=None, max_length=120)

    @field_validator("name")
    @classmethod
    def _check_name(cls, value: str | dict) -> str | dict:
        return _validate_i18n_name(value, 120)


class MealService(BaseModel):
    meal: str = Field(min_length=1, max_length=40)
    time_from: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    time_to: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
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
