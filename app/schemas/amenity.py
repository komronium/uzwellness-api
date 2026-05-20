import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import Translations


class AmenityCreate(BaseModel):
    name: Translations = Field(default_factory=Translations)
    description: Translations = Field(default_factory=Translations)
    category: str = Field(min_length=1, max_length=60)
    icon: str | None = Field(default=None, max_length=100)


class AmenityUpdate(BaseModel):
    name: Translations | None = None
    description: Translations | None = None
    category: str | None = Field(default=None, min_length=1, max_length=60)
    icon: str | None = None


class AmenityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: dict
    description: dict
    category: str
    icon: str | None
    created_at: datetime


class AmenityList(BaseModel):
    items: list[AmenityRead]
    total: int
    limit: int
    offset: int


class TreatmentProgramCreate(BaseModel):
    sanatorium_id: uuid.UUID
    name: Translations = Field(default_factory=Translations)
    description: Translations = Field(default_factory=Translations)
    min_nights: int | None = Field(default=None, ge=1)
    max_nights: int | None = Field(default=None, ge=1)
    duration_minutes: int | None = Field(default=None, ge=1)
    price: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, max_length=3)
    instructor_name: str | None = Field(default=None, max_length=255)
    instructor_bio: Translations = Field(default_factory=Translations)
    group_size_min: int | None = Field(default=None, ge=1)
    group_size_max: int | None = Field(default=None, ge=1)
    what_to_bring: Translations = Field(default_factory=Translations)
    amenity_ids: list[uuid.UUID] = Field(default_factory=list)


class TreatmentProgramUpdate(BaseModel):
    name: Translations | None = None
    description: Translations | None = None
    min_nights: int | None = Field(default=None, ge=1)
    max_nights: int | None = Field(default=None, ge=1)
    duration_minutes: int | None = Field(default=None, ge=1)
    price: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, max_length=3)
    instructor_name: str | None = Field(default=None, max_length=255)
    instructor_bio: Translations | None = None
    group_size_min: int | None = Field(default=None, ge=1)
    group_size_max: int | None = Field(default=None, ge=1)
    what_to_bring: Translations | None = None
    is_active: bool | None = None
    amenity_ids: list[uuid.UUID] | None = None


class TreatmentProgramRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sanatorium_id: uuid.UUID
    name: dict
    description: dict
    min_nights: int | None
    max_nights: int | None
    duration_minutes: int | None
    price: Decimal | None
    currency: str | None
    instructor_name: str | None
    instructor_bio: dict
    group_size_min: int | None
    group_size_max: int | None
    what_to_bring: dict
    is_active: bool
    amenities: list[AmenityRead]
    created_at: datetime
    updated_at: datetime


class TreatmentProgramList(BaseModel):
    items: list[TreatmentProgramRead]
    total: int
    limit: int
    offset: int
