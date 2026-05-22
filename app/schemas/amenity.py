import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.utils import pick_locale
from app.schemas.common import Translations, TranslationsCreate


class AmenityCreate(BaseModel):
    name: TranslationsCreate
    description: TranslationsCreate
    category: str = Field(min_length=1, max_length=60)
    icon: str | None = Field(default=None, max_length=100)


class AmenityUpdate(BaseModel):
    name: Translations | None = None
    description: Translations | None = None
    category: str | None = Field(default=None, min_length=1, max_length=60)
    icon: str | None = None


class AmenityRead(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    category: str
    icon: str | None
    created_at: datetime

    @classmethod
    def from_obj(cls, obj, locale: str) -> "AmenityRead":
        return cls(
            id=obj.id,
            name=pick_locale(obj.name, locale),
            description=pick_locale(obj.description, locale),
            category=obj.category,
            icon=obj.icon,
            created_at=obj.created_at,
        )


class AmenityAdminRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: dict
    description: dict
    category: str
    icon: str | None
    created_at: datetime


class AmenityList(BaseModel):
    items: list[AmenityRead]
    total: int
    limit: int
    offset: int


class AmenityAdminList(BaseModel):
    items: list[AmenityAdminRead]
    total: int
    limit: int
    offset: int
