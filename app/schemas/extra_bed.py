import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.core.utils import pick_locale
from app.schemas.common import Page, Translations, TranslationsCreate


class ExtraBedConfigCreate(BaseModel):
    sanatorium_id: uuid.UUID
    name: TranslationsCreate
    description: TranslationsCreate
    price_per_night: Decimal = Field(ge=0, decimal_places=2)
    currency: str = Field(pattern=r"^(UZS|USD)$")
    max_count: int = Field(default=10, ge=1)


class ExtraBedConfigUpdate(BaseModel):
    name: Translations | None = None
    description: Translations | None = None
    price_per_night: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    currency: str | None = Field(default=None, pattern=r"^(UZS|USD)$")
    max_count: int | None = Field(default=None, ge=1)
    is_active: bool | None = None


class ExtraBedConfigRead(BaseModel):
    """Public read: i18n fields resolved to a single locale string."""

    id: uuid.UUID
    sanatorium_id: uuid.UUID
    name: str
    description: str
    price_per_night: Decimal
    currency: str
    max_count: int
    is_active: bool
    created_at: datetime

    @classmethod
    def from_obj(cls, obj, locale: str) -> "ExtraBedConfigRead":
        return cls(
            id=obj.id,
            sanatorium_id=obj.sanatorium_id,
            name=pick_locale(obj.name, locale),
            description=pick_locale(obj.description, locale),
            price_per_night=obj.price_per_night,
            currency=obj.currency,
            max_count=obj.max_count,
            is_active=obj.is_active,
            created_at=obj.created_at,
        )


class ExtraBedConfigAdminRead(BaseModel):
    """Admin read: i18n fields returned as {uz, ru, en} dicts."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sanatorium_id: uuid.UUID
    name: dict
    description: dict
    price_per_night: Decimal
    currency: str
    max_count: int
    is_active: bool
    created_at: datetime


class ExtraBedConfigList(Page[ExtraBedConfigRead]):
    pass


class ExtraBedConfigAdminList(Page[ExtraBedConfigAdminRead]):
    pass


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
