import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.sanatorium import Translations  # re-exported for room name translations


class RoomCategoryCreate(BaseModel):
    sanatorium_id: uuid.UUID
    name: Translations = Field(default_factory=Translations)
    capacity: int = Field(ge=1)
    base_price: Decimal = Field(ge=0, decimal_places=2)
    base_currency: str = Field(pattern=r"^(UZS|USD)$")
    min_nights: int = Field(default=1, ge=1)


class RoomCategoryUpdate(BaseModel):
    name: Translations | None = None
    capacity: int | None = Field(default=None, ge=1)
    base_price: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    base_currency: str | None = Field(default=None, pattern=r"^(UZS|USD)$")
    markup_percent: Decimal | None = Field(default=None, ge=0, le=100, decimal_places=2)
    min_nights: int | None = Field(default=None, ge=1)
    is_active: bool | None = None


class RoomCategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sanatorium_id: uuid.UUID
    name: Translations
    capacity: int
    base_price: Decimal
    base_currency: str
    markup_percent: Decimal
    min_nights: int
    is_active: bool
    final_price: Decimal
    final_price_uzs: Decimal | None
    final_price_usd: Decimal | None
    created_at: datetime
    updated_at: datetime


class RoomCategoryList(BaseModel):
    items: list[RoomCategoryRead]
    total: int
    limit: int
    offset: int


class AvailabilityBulkCreate(BaseModel):
    date_from: date
    date_to: date
    units_total: int = Field(ge=1)
    overwrite: bool = False


class AvailabilityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: date
    units_available: int
    units_total: int


