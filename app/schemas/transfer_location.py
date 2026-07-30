import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.core.utils import pick_locale
from app.models.transfer_location import TransferLocationKind
from app.schemas.common import Page, Translations, TranslationsCreate


class TransferLocationCreate(BaseModel):
    name: TranslationsCreate
    kind: TransferLocationKind
    is_active: bool = True


class TransferLocationUpdate(BaseModel):
    name: Translations | None = None
    kind: TransferLocationKind | None = None
    is_active: bool | None = None


class _TransferLocationReadCommon(BaseModel):
    id: uuid.UUID
    kind: TransferLocationKind
    is_active: bool
    created_at: datetime
    updated_at: datetime


class TransferLocationRead(_TransferLocationReadCommon):
    name: str

    @classmethod
    def from_obj(cls, obj, locale: str) -> "TransferLocationRead":
        return cls(
            id=obj.id,
            name=pick_locale(obj.name, locale),
            kind=obj.kind,
            is_active=obj.is_active,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )


class TransferLocationAdminRead(_TransferLocationReadCommon):
    model_config = ConfigDict(from_attributes=True)
    name: dict


class TransferLocationList(Page[TransferLocationRead]):
    pass


class TransferLocationAdminList(Page[TransferLocationAdminRead]):
    pass
