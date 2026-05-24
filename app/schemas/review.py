import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ReviewCreate(BaseModel):
    reviewer_name: str = Field(min_length=1, max_length=120)
    reviewer_country: str | None = Field(default=None, max_length=60)
    traveler_type: str | None = Field(default=None, max_length=30)
    rating: int = Field(ge=1, le=5)
    cleanliness: int | None = Field(default=None, ge=1, le=5)
    location: int | None = Field(default=None, ge=1, le=5)
    service: int | None = Field(default=None, ge=1, le=5)
    value: int | None = Field(default=None, ge=1, le=5)
    food: int | None = Field(default=None, ge=1, le=5)
    body: str = Field(min_length=10, max_length=3000)


class ReviewUpdate(BaseModel):
    is_visible: bool


class ReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sanatorium_id: uuid.UUID
    user_id: uuid.UUID | None
    reviewer_name: str
    reviewer_country: str | None
    traveler_type: str | None
    rating: int
    cleanliness: int | None
    location: int | None
    service: int | None
    value: int | None
    food: int | None
    body: str
    is_visible: bool
    created_at: datetime


class ReviewList(BaseModel):
    items: list[ReviewRead]
    total: int
    limit: int
    offset: int
