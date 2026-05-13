import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.sanatorium import SanatoriumStatus
from app.schemas.amenity import AmenityRead
from app.schemas.common import Translations

TREATMENT_FOCUS_VALUES = frozenset({
    "cardiovascular", "digestive", "musculoskeletal",
    "respiratory", "neurological", "dermatology",
    "endocrine", "wellness",
})


class SanatoriumImageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    url: str
    order: int
    is_primary: bool
    caption: str | None
    created_at: datetime


class SanatoriumBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: Translations = Field(default_factory=Translations)
    city: str = Field(min_length=1, max_length=120)
    address: str = Field(min_length=1, max_length=500)
    lat: Decimal | None = Field(default=None, ge=-90, le=90)
    lng: Decimal | None = Field(default=None, ge=-180, le=180)
    phone: str | None = Field(default=None, max_length=30)
    stars: int = Field(ge=1, le=5)
    treatment_focuses: list[str] = Field(default_factory=list)


class SanatoriumCreate(SanatoriumBase):
    slug: str | None = Field(default=None, max_length=255)
    admin_user_id: uuid.UUID | None = None
    amenity_ids: list[uuid.UUID] = Field(default_factory=list)


class SanatoriumUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    slug: str | None = Field(default=None, max_length=255)
    description: Translations | None = None
    city: str | None = Field(default=None, min_length=1, max_length=120)
    address: str | None = Field(default=None, min_length=1, max_length=500)
    lat: Decimal | None = Field(default=None, ge=-90, le=90)
    lng: Decimal | None = Field(default=None, ge=-180, le=180)
    phone: str | None = Field(default=None, max_length=30)
    stars: int | None = Field(default=None, ge=1, le=5)
    admin_user_id: uuid.UUID | None = None
    treatment_focuses: list[str] | None = None
    amenity_ids: list[uuid.UUID] | None = None


class SanatoriumRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    description: Translations
    city: str
    address: str
    lat: Decimal | None
    lng: Decimal | None
    phone: str | None
    stars: int
    status: SanatoriumStatus
    treatment_focuses: list[str]
    avg_rating: Decimal | None
    review_count: int
    admin_user_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    images: list[SanatoriumImageRead] = Field(default_factory=list)
    amenities: list[AmenityRead] = Field(default_factory=list)


class SanatoriumList(BaseModel):
    items: list[SanatoriumRead]
    total: int
    limit: int
    offset: int
