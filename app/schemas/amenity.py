import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import Translations


class AmenityCreate(BaseModel):
    name: Translations = Field(default_factory=Translations)
    category: str = Field(min_length=1, max_length=60)
    icon: str | None = Field(default=None, max_length=100)


class AmenityUpdate(BaseModel):
    name: Translations | None = None
    category: str | None = Field(default=None, min_length=1, max_length=60)
    icon: str | None = None


class AmenityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: dict
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
    min_nights: int = Field(ge=1)
    max_nights: int | None = Field(default=None, ge=1)
    amenity_ids: list[uuid.UUID] = Field(default_factory=list)


class TreatmentProgramUpdate(BaseModel):
    name: Translations | None = None
    min_nights: int | None = Field(default=None, ge=1)
    max_nights: int | None = Field(default=None, ge=1)
    is_active: bool | None = None
    amenity_ids: list[uuid.UUID] | None = None


class TreatmentProgramRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sanatorium_id: uuid.UUID
    name: dict
    min_nights: int
    max_nights: int | None
    is_active: bool
    amenities: list[AmenityRead]
    created_at: datetime
    updated_at: datetime


class TreatmentProgramList(BaseModel):
    items: list[TreatmentProgramRead]
    total: int
    limit: int
    offset: int
