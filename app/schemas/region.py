import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.utils import pick_locale
from app.schemas.common import Translations, TranslationsCreate


class RegionCreate(BaseModel):
    slug: str | None = Field(default=None, max_length=80)
    name: TranslationsCreate
    is_active: bool = True


class RegionUpdate(BaseModel):
    slug: str | None = Field(default=None, max_length=80)
    name: Translations | None = None
    is_active: bool | None = None


class _RegionReadCommon(BaseModel):
    id: uuid.UUID
    slug: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class RegionRead(_RegionReadCommon):
    name: str

    @classmethod
    def from_obj(cls, obj, locale: str) -> "RegionRead":
        return cls(
            id=obj.id,
            slug=obj.slug,
            name=pick_locale(obj.name, locale),
            is_active=obj.is_active,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )


class RegionAdminRead(_RegionReadCommon):
    model_config = ConfigDict(from_attributes=True)
    name: dict


class RegionList(BaseModel):
    items: list[RegionRead]
    total: int
    limit: int
    offset: int


class RegionAdminList(BaseModel):
    items: list[RegionAdminRead]
    total: int
    limit: int
    offset: int
