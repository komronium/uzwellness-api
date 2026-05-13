import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import Translations


class ExtraBedConfigCreate(BaseModel):
    sanatorium_id: uuid.UUID
    name: Translations = Field(default_factory=Translations)
    price_per_night: Decimal = Field(ge=0, decimal_places=2)
    currency: str = Field(pattern=r"^(UZS|USD)$")
    max_count: int = Field(default=10, ge=1)


class ExtraBedConfigUpdate(BaseModel):
    name: Translations | None = None
    price_per_night: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    currency: str | None = Field(default=None, pattern=r"^(UZS|USD)$")
    max_count: int | None = Field(default=None, ge=1)
    is_active: bool | None = None


class ExtraBedConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sanatorium_id: uuid.UUID
    name: dict
    price_per_night: Decimal
    currency: str
    max_count: int
    is_active: bool
    created_at: datetime


class ExtraBedConfigList(BaseModel):
    items: list[ExtraBedConfigRead]
    total: int
    limit: int
    offset: int


class ExtraBedItem(BaseModel):
    config_id: uuid.UUID
    count: int = Field(ge=1)


class BookingExtraBedRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    config_id: uuid.UUID | None
    name_snapshot: dict
    price_per_night_snapshot: Decimal
    currency: str
    count: int
    total_price: Decimal
