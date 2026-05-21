import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.core.utils import pick_locale
from app.models.package import PackageItemType
from app.schemas.common import Translations, TranslationsCreate


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
    display_order: int

    @classmethod
    def from_obj(cls, obj, locale: str) -> "PackageItemRead":
        return cls(
            id=obj.id,
            item_type=obj.item_type,
            title=pick_locale(obj.title, locale),
            description=pick_locale(obj.description, locale),
            is_included=obj.is_included,
            extra_price=obj.extra_price,
            display_order=obj.display_order,
        )


class PackageItemAdminRead(BaseModel):
    """Admin read: i18n fields returned as {uz, ru, en} dicts."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    item_type: PackageItemType
    title: dict
    description: dict
    is_included: bool
    extra_price: Decimal | None
    display_order: int


# ── Package ────────────────────────────────────────────────────────────────


class PackageCreate(BaseModel):
    slug: str | None = Field(default=None, max_length=255)
    title: TranslationsCreate
    description: TranslationsCreate
    hero_image_url: str | None = Field(default=None, max_length=500)
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
    hero_image_url: str | None = Field(default=None, max_length=500)
    duration_nights: int | None = Field(default=None, ge=1)
    base_price: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    currency: str | None = Field(default=None, pattern=r"^(UZS|USD)$")
    room_id: uuid.UUID | None = None
    is_active: bool | None = None


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
    created_at: datetime
    updated_at: datetime


class PackageRead(_PackageReadCommon):
    """Public read."""

    title: str
    description: str
    items: list[PackageItemRead] = Field(default_factory=list)

    @classmethod
    def from_obj(cls, obj, locale: str) -> "PackageRead":
        return cls(
            id=obj.id,
            slug=obj.slug,
            title=pick_locale(obj.title, locale),
            description=pick_locale(obj.description, locale),
            hero_image_url=obj.hero_image_url,
            duration_nights=obj.duration_nights,
            base_price=obj.base_price,
            currency=obj.currency,
            sanatorium_id=obj.sanatorium_id,
            room_id=obj.room_id,
            is_active=obj.is_active,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
            items=[PackageItemRead.from_obj(i, locale) for i in obj.items],
        )


class PackageAdminRead(_PackageReadCommon):
    """Admin read."""

    model_config = ConfigDict(from_attributes=True)

    title: dict
    description: dict
    items: list[PackageItemAdminRead] = Field(default_factory=list)


class PackageList(BaseModel):
    items: list[PackageRead]
    total: int
    limit: int
    offset: int


class PackageAdminList(BaseModel):
    items: list[PackageAdminRead]
    total: int
    limit: int
    offset: int
