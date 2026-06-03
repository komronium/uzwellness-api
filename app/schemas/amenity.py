import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.utils import pick_locale
from app.models.amenity import AmenityScope
from app.schemas.common import Translations, TranslationsCreate


class AmenityCreate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=80)
    name: TranslationsCreate
    description: TranslationsCreate
    category: str = Field(min_length=1, max_length=60)
    scope: AmenityScope = AmenityScope.BOTH
    icon: str | None = Field(default=None, max_length=100)
    display_order: int = Field(default=0, ge=0)
    is_active: bool = True


class AmenityUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=80)
    name: Translations | None = None
    description: Translations | None = None
    category: str | None = Field(default=None, min_length=1, max_length=60)
    scope: AmenityScope | None = None
    icon: str | None = None
    display_order: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class AmenityRead(BaseModel):
    id: uuid.UUID
    code: str | None
    name: str
    description: str
    category: str
    scope: AmenityScope
    icon: str | None
    display_order: int
    is_active: bool
    created_at: datetime

    @classmethod
    def from_obj(cls, obj, locale: str) -> "AmenityRead":
        return cls(
            id=obj.id,
            code=obj.code,
            name=pick_locale(obj.name, locale),
            description=pick_locale(obj.description, locale),
            category=obj.category,
            scope=obj.scope,
            icon=obj.icon,
            display_order=obj.display_order,
            is_active=obj.is_active,
            created_at=obj.created_at,
        )


class AmenityAdminRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str | None
    name: dict
    description: dict
    category: str
    scope: AmenityScope
    icon: str | None
    display_order: int
    is_active: bool
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
