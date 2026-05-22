import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.core.utils import pick_locale
from app.schemas.common import Translations, TranslationsCreate


class DestinationCreate(BaseModel):
    slug: str | None = Field(default=None, max_length=120)
    name: TranslationsCreate
    tagline: TranslationsCreate
    description: Translations = Field(default_factory=Translations)
    hero_image: str | None = Field(default=None, max_length=500)
    country: str = Field(default="Uzbekistan", max_length=80)
    lat: Decimal | None = Field(default=None, ge=-90, le=90)
    lng: Decimal | None = Field(default=None, ge=-180, le=180)
    is_active: bool = True


class DestinationUpdate(BaseModel):
    slug: str | None = Field(default=None, max_length=120)
    name: Translations | None = None
    tagline: Translations | None = None
    description: Translations | None = None
    hero_image: str | None = Field(default=None, max_length=500)
    country: str | None = Field(default=None, max_length=80)
    lat: Decimal | None = Field(default=None, ge=-90, le=90)
    lng: Decimal | None = Field(default=None, ge=-180, le=180)
    is_active: bool | None = None


class _DestinationReadCommon(BaseModel):
    id: uuid.UUID
    slug: str
    hero_image: str | None
    country: str
    lat: Decimal | None
    lng: Decimal | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class DestinationRead(_DestinationReadCommon):
    name: str
    tagline: str
    description: str

    @classmethod
    def from_obj(cls, obj, locale: str) -> "DestinationRead":
        return cls(
            id=obj.id,
            slug=obj.slug,
            name=pick_locale(obj.name, locale),
            tagline=pick_locale(obj.tagline, locale),
            description=pick_locale(obj.description, locale),
            hero_image=obj.hero_image,
            country=obj.country,
            lat=obj.lat,
            lng=obj.lng,
            is_active=obj.is_active,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )


class DestinationAdminRead(_DestinationReadCommon):
    model_config = ConfigDict(from_attributes=True)
    name: dict
    tagline: dict
    description: dict


class DestinationTileRead(DestinationRead):
    """Homepage tile: destination + aggregate sanatorium stats."""

    sanatoriums_count: int
    min_price_usd: Decimal | None

    @classmethod
    def from_aggregate(
        cls,
        obj,
        locale: str,
        *,
        sanatoriums_count: int,
        min_price_usd: Decimal | None,
    ) -> "DestinationTileRead":
        base = DestinationRead.from_obj(obj, locale)
        return cls(
            **base.model_dump(),
            sanatoriums_count=sanatoriums_count,
            min_price_usd=min_price_usd,
        )


class DestinationList(BaseModel):
    items: list[DestinationRead]
    total: int
    limit: int
    offset: int


class DestinationAdminList(BaseModel):
    items: list[DestinationAdminRead]
    total: int
    limit: int
    offset: int


class DestinationTileList(BaseModel):
    items: list[DestinationTileRead]
    total: int
