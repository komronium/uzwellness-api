import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import Translations


class RoomImageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    url: str
    order: int
    is_primary: bool
    is_video: bool
    is_360: bool
    category: str | None
    caption: str | None
    caption_i18n: dict
    alt_text: dict
    tags: list[str]
    created_at: datetime


class RoomImageUpdate(BaseModel):
    is_primary: bool | None = None
    is_video: bool | None = None
    is_360: bool | None = None
    category: str | None = Field(default=None, max_length=40)
    order: int | None = Field(default=None, ge=0)
    caption: str | None = Field(default=None, max_length=255)
    caption_i18n: Translations | None = None
    alt_text: Translations | None = None
    tags: list[str] | None = None
