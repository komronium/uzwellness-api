import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.core.currency import CurrencyConverter
from app.core.utils import pick_locale
from app.models.package import PackageItemType
from app.schemas.common import Page, Translations, TranslationsCreate


class PackageItemCreate(BaseModel):
    item_type: PackageItemType
    title: TranslationsCreate
    description: Translations = Field(default_factory=Translations)
    is_included: bool = True
    extra_price: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    display_order: int = Field(default=0, ge=0)


class PackageItemUpdate(BaseModel):
    item_type: PackageItemType | None = None
    title: Translations | None = None
    description: Translations | None = None
    is_included: bool | None = None
    extra_price: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    display_order: int | None = Field(default=None, ge=0)


class PackageItemRead(BaseModel):
    """Public read: i18n fields resolved to a single locale string."""

    id: uuid.UUID
    item_type: PackageItemType
    title: str
    description: str
    is_included: bool
    extra_price: Decimal | None
    display_extra_price: Decimal | None = None
    display_order: int

    @classmethod
    def from_obj(
        cls,
        obj,
        locale: str,
        currency: str | None = None,
        converter: CurrencyConverter | None = None,
    ) -> "PackageItemRead":
        display_extra_price = None
        if converter is not None and obj.extra_price is not None and currency:
            display_extra_price = converter.convert(obj.extra_price, currency)
        return cls(
            id=obj.id,
            item_type=obj.item_type,
            title=pick_locale(obj.title, locale),
            description=pick_locale(obj.description, locale),
            is_included=obj.is_included,
            extra_price=obj.extra_price,
            display_extra_price=display_extra_price,
            display_order=obj.display_order,
        )


class PackageItemAdminRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    item_type: PackageItemType
    title: dict
    description: dict
    is_included: bool
    extra_price: Decimal | None
    display_order: int


class PackageCreate(BaseModel):
    slug: str | None = Field(default=None, max_length=255)
    title: TranslationsCreate
    description: TranslationsCreate
    duration_nights: int = Field(ge=1)
    base_price: Decimal = Field(ge=0, decimal_places=2)
    currency: str = Field(pattern=r"^(UZS|USD)$")
    sanatorium_id: uuid.UUID
    room_id: uuid.UUID
    items: list[PackageItemCreate] = Field(default_factory=list)


class PackageUpdate(BaseModel):
    slug: str | None = Field(default=None, max_length=255)
    title: Translations | None = None
    description: Translations | None = None
    duration_nights: int | None = Field(default=None, ge=1)
    base_price: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    currency: str | None = Field(default=None, pattern=r"^(UZS|USD)$")
    room_id: uuid.UUID | None = None
    is_active: bool | None = None
    is_featured: bool | None = None
    display_order: int | None = Field(default=None, ge=0)


class _PackageReadCommon(BaseModel):
    id: uuid.UUID
    slug: str
    hero_image_url: str | None
    duration_nights: int
    base_price: Decimal
    currency: str
    sanatorium_id: uuid.UUID
    room_id: uuid.UUID
    is_active: bool
    is_featured: bool
    display_order: int
    created_at: datetime
    updated_at: datetime


class PackageRead(_PackageReadCommon):
    """Public read."""

    title: str
    description: str
    display_price: Decimal | None = None
    display_currency: str | None = None
    items: list[PackageItemRead] = Field(default_factory=list)

    @classmethod
    def from_obj(
        cls, obj, locale: str, converter: CurrencyConverter | None = None
    ) -> "PackageRead":
        display_price = None
        display_currency = None
        if converter is not None:
            display_price = converter.convert(obj.base_price, obj.currency)
            display_currency = converter.target
        return cls(
            id=obj.id,
            slug=obj.slug,
            title=pick_locale(obj.title, locale),
            description=pick_locale(obj.description, locale),
            hero_image_url=obj.hero_image_url,
            duration_nights=obj.duration_nights,
            base_price=obj.base_price,
            currency=obj.currency,
            display_price=display_price,
            display_currency=display_currency,
            sanatorium_id=obj.sanatorium_id,
            room_id=obj.room_id,
            is_active=obj.is_active,
            is_featured=obj.is_featured,
            display_order=obj.display_order,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
            items=[
                PackageItemRead.from_obj(i, locale, obj.currency, converter)
                for i in obj.items
            ],
        )


class PackageAdminRead(_PackageReadCommon):
    """Admin read."""

    model_config = ConfigDict(from_attributes=True)

    title: dict
    description: dict
    items: list[PackageItemAdminRead] = Field(default_factory=list)


class PackageList(Page[PackageRead]):
    pass


class PackageAdminList(Page[PackageAdminRead]):
    pass
