import uuid
from datetime import date
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.review import ReviewAppealStatus, ReviewReplyStatus, ReviewSource
from app.schemas.common import Page


class ReviewCreate(BaseModel):
    booking_id: uuid.UUID | None = None
    room_id: uuid.UUID | None = None
    source: ReviewSource = ReviewSource.UZWELLNESS
    external_id: str | None = Field(default=None, max_length=120)
    external_url: str | None = Field(default=None, max_length=500)
    reviewer_name: str = Field(min_length=1, max_length=120)
    reviewer_country: str | None = Field(default=None, max_length=60)
    reviewer_avatar_url: str | None = Field(default=None, max_length=500)
    traveler_type: str | None = Field(default=None, max_length=30)
    language: str | None = Field(default=None, max_length=10)
    stayed_at: date | None = None
    stayed_room_name: str | None = Field(default=None, max_length=160)
    rating: int = Field(ge=1, le=5)
    score_label: str | None = Field(default=None, max_length=40)
    cleanliness: int | None = Field(default=None, ge=1, le=5)
    amenities: int | None = Field(default=None, ge=1, le=5)
    location: int | None = Field(default=None, ge=1, le=5)
    service: int | None = Field(default=None, ge=1, le=5)
    treatment: int | None = Field(default=None, ge=1, le=5)
    value: int | None = Field(default=None, ge=1, le=5)
    food: int | None = Field(default=None, ge=1, le=5)
    body: str = Field(min_length=10, max_length=3000)
    translated_body: str | None = Field(default=None, max_length=3000)
    positive_tags: list[str] = Field(default_factory=list)
    negative_tags: list[str] = Field(default_factory=list)
    photos: list[dict] = Field(default_factory=list)


class ReviewUpdate(BaseModel):
    is_visible: bool


class ReviewReplyUpdate(BaseModel):
    body: str = Field(min_length=1, max_length=2000)
    language: str | None = Field(default=None, max_length=10)


class ReviewAppealCreate(BaseModel):
    reason: str = Field(min_length=5, max_length=2000)


class ReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sanatorium_id: uuid.UUID
    user_id: uuid.UUID | None
    booking_id: uuid.UUID | None
    room_id: uuid.UUID | None
    source: ReviewSource
    external_id: str | None
    external_url: str | None
    reviewer_name: str
    reviewer_country: str | None
    reviewer_avatar_url: str | None
    traveler_type: str | None
    language: str | None
    stayed_at: date | None
    stayed_room_name: str | None
    rating: int
    score_label: str | None
    cleanliness: int | None
    amenities: int | None
    location: int | None
    service: int | None
    treatment: int | None
    value: int | None
    food: int | None
    body: str
    translated_body: str | None
    positive_tags: list[str]
    negative_tags: list[str]
    photos: list[dict]
    reply_body: str | None
    reply_language: str | None
    reply_status: ReviewReplyStatus
    replied_at: datetime | None
    replied_by_user_id: uuid.UUID | None
    appeal_status: ReviewAppealStatus
    appeal_reason: str | None
    appealed_at: datetime | None
    is_visible: bool
    created_at: datetime


class ReviewList(Page[ReviewRead]):
    pass


class ReviewTagCount(BaseModel):
    tag: str
    count: int


class ReviewRatingBreakdown(BaseModel):
    cleanliness: Decimal | None = None
    amenities: Decimal | None = None
    location: Decimal | None = None
    service: Decimal | None = None
    treatment: Decimal | None = None
    value: Decimal | None = None
    food: Decimal | None = None


class ReviewAdminSummary(BaseModel):
    total_reviews: int
    awaiting_reply: int
    negative_reviews: int
    reviews_with_photos: int
    average_rating: Decimal | None
    reply_rate: Decimal
    rating_breakdown: ReviewRatingBreakdown
    positive_tags: list[ReviewTagCount]
    negative_tags: list[ReviewTagCount]
