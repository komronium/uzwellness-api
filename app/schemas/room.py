import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import Translations


class RoomCreate(BaseModel):
    sanatorium_id: uuid.UUID
    name: Translations = Field(default_factory=Translations)
    room_amenities: list[str] = Field(default_factory=list)
    capacity: int = Field(ge=1)
    base_price: Decimal = Field(ge=0, decimal_places=2)
    base_price_weekend: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    base_currency: str = Field(pattern=r"^(UZS|USD)$")
    min_nights: int = Field(default=1, ge=1)


class RoomUpdate(BaseModel):
    name: Translations | None = None
    room_amenities: list[str] | None = None
    capacity: int | None = Field(default=None, ge=1)
    base_price: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    base_price_weekend: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    base_currency: str | None = Field(default=None, pattern=r"^(UZS|USD)$")
    markup_percent: Decimal | None = Field(default=None, ge=0, le=100, decimal_places=2)
    discount_percent: Decimal | None = Field(default=None, ge=0, le=100, decimal_places=2)
    b2b_discount_percent: Decimal | None = Field(
        default=None, ge=0, le=100, decimal_places=2
    )
    min_nights: int | None = Field(default=None, ge=1)
    is_active: bool | None = None


class RoomRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sanatorium_id: uuid.UUID
    name: dict
    room_amenities: list[str] = Field(default_factory=list)
    capacity: int
    base_price: Decimal
    base_price_weekend: Decimal | None = None
    base_currency: str
    markup_percent: Decimal
    discount_percent: Decimal | None = None
    b2b_discount_percent: Decimal | None = None
    min_nights: int
    is_active: bool
    final_price: Decimal = Decimal("0")
    final_price_uzs: Decimal | None = None
    final_price_usd: Decimal | None = None
    final_price_weekend: Decimal | None = None
    final_price_weekend_uzs: Decimal | None = None
    final_price_weekend_usd: Decimal | None = None
    b2b_final_price: Decimal | None = None
    b2b_final_price_uzs: Decimal | None = None
    b2b_final_price_usd: Decimal | None = None
    b2b_final_price_weekend: Decimal | None = None
    b2b_final_price_weekend_uzs: Decimal | None = None
    b2b_final_price_weekend_usd: Decimal | None = None
    created_at: datetime
    updated_at: datetime


class RoomList(BaseModel):
    items: list[RoomRead]
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
