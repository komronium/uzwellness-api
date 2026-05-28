import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.utils import pick_locale
from app.schemas.common import Translations, TranslationsCreate


class TreatmentFocusCreate(BaseModel):
    slug: str | None = Field(default=None, min_length=1, max_length=120)
    name: TranslationsCreate
    description: Translations = Field(default_factory=Translations)
    icon: str | None = Field(default=None, max_length=80)
    display_order: int = Field(default=0, ge=0)
    is_active: bool = True


class TreatmentFocusUpdate(BaseModel):
    slug: str | None = Field(default=None, min_length=1, max_length=120)
    name: Translations | None = None
    description: Translations | None = None
    icon: str | None = Field(default=None, max_length=80)
    display_order: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class _TreatmentFocusReadCommon(BaseModel):
    id: uuid.UUID
    slug: str
    image_url: str | None
    icon: str | None
    display_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class TreatmentFocusRead(_TreatmentFocusReadCommon):
    name: str
    description: str

    @classmethod
    def from_obj(cls, obj, locale: str) -> "TreatmentFocusRead":
        return cls(
            id=obj.id,
            slug=obj.slug,
            name=pick_locale(obj.name, locale),
            description=pick_locale(obj.description, locale),
            image_url=obj.image_url,
            icon=obj.icon,
            display_order=obj.display_order,
            is_active=obj.is_active,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )


class TreatmentFocusAdminRead(_TreatmentFocusReadCommon):
    model_config = ConfigDict(from_attributes=True)

    name: dict
    description: dict


class TreatmentFocusTileRead(TreatmentFocusRead):
    programs_count: int
    sanatoriums_count: int


class TreatmentFocusList(BaseModel):
    items: list[TreatmentFocusRead]
    total: int
    limit: int
    offset: int


class TreatmentFocusAdminList(BaseModel):
    items: list[TreatmentFocusAdminRead]
    total: int
    limit: int
    offset: int


class TreatmentFocusTileList(BaseModel):
    items: list[TreatmentFocusTileRead]
    total: int
