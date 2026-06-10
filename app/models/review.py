from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    SmallInteger,
    String,
    Text,
    Uuid,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin
from app.core.ids import uuid7

if TYPE_CHECKING:
    from app.models.booking import Booking
    from app.models.room import Room
    from app.models.sanatorium import Sanatorium
    from app.models.user import User


class ReviewSource(StrEnum):
    UZWELLNESS = "uzwellness"
    TRIP_COM = "trip_com"
    QUNAR = "qunar"
    LY_COM = "ly_com"
    GOOGLE = "google"
    BOOKING_COM = "booking_com"


class ReviewReplyStatus(StrEnum):
    AWAITING_REPLY = "awaiting_reply"
    REPLIED = "replied"
    NOT_REQUIRED = "not_required"


class ReviewAppealStatus(StrEnum):
    NONE = "none"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"


class SanatoriumReview(TimestampMixin, Base):
    __tablename__ = "sanatorium_reviews"
    __table_args__ = (
        CheckConstraint("rating BETWEEN 1 AND 10", name="ck_reviews_rating_range"),
        CheckConstraint(
            "cleanliness IS NULL OR cleanliness BETWEEN 1 AND 10",
            name="ck_reviews_cleanliness_range",
        ),
        CheckConstraint(
            "amenities IS NULL OR amenities BETWEEN 1 AND 10",
            name="ck_reviews_amenities_range",
        ),
        CheckConstraint(
            "location IS NULL OR location BETWEEN 1 AND 10",
            name="ck_reviews_location_range",
        ),
        CheckConstraint(
            "service IS NULL OR service BETWEEN 1 AND 10",
            name="ck_reviews_service_range",
        ),
        CheckConstraint(
            "treatment IS NULL OR treatment BETWEEN 1 AND 10",
            name="ck_reviews_treatment_range",
        ),
        CheckConstraint(
            "value IS NULL OR value BETWEEN 1 AND 10",
            name="ck_reviews_value_range",
        ),
        CheckConstraint(
            "food IS NULL OR food BETWEEN 1 AND 10",
            name="ck_reviews_food_range",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    sanatorium_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("sanatoriums.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    booking_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("bookings.id", ondelete="SET NULL"), index=True
    )
    room_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("rooms.id", ondelete="SET NULL"), index=True
    )
    source: Mapped[ReviewSource] = mapped_column(
        SQLEnum(
            ReviewSource,
            native_enum=False,
            length=30,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        default=ReviewSource.UZWELLNESS,
        server_default=ReviewSource.UZWELLNESS.value,
        index=True,
    )
    external_id: Mapped[str | None] = mapped_column(String(120), index=True)
    external_url: Mapped[str | None] = mapped_column(String(500))
    reviewer_name: Mapped[str] = mapped_column(String(120), nullable=False)
    reviewer_country: Mapped[str | None] = mapped_column(String(60))
    reviewer_avatar_url: Mapped[str | None] = mapped_column(String(500))
    traveler_type: Mapped[str | None] = mapped_column(String(30))
    language: Mapped[str | None] = mapped_column(String(10))
    stayed_at: Mapped[date | None] = mapped_column(Date)
    stayed_room_name: Mapped[str | None] = mapped_column(String(160))
    rating: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    score_label: Mapped[str | None] = mapped_column(String(40))
    cleanliness: Mapped[int | None] = mapped_column(SmallInteger)
    amenities: Mapped[int | None] = mapped_column(SmallInteger)
    location: Mapped[int | None] = mapped_column(SmallInteger)
    service: Mapped[int | None] = mapped_column(SmallInteger)
    treatment: Mapped[int | None] = mapped_column(SmallInteger)
    value: Mapped[int | None] = mapped_column(SmallInteger)
    food: Mapped[int | None] = mapped_column(SmallInteger)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    translated_body: Mapped[str | None] = mapped_column(Text)
    positive_tags: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    negative_tags: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    photos: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    reply_body: Mapped[str | None] = mapped_column(Text)
    reply_language: Mapped[str | None] = mapped_column(String(10))
    reply_status: Mapped[ReviewReplyStatus] = mapped_column(
        SQLEnum(
            ReviewReplyStatus,
            native_enum=False,
            length=30,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        default=ReviewReplyStatus.AWAITING_REPLY,
        server_default=ReviewReplyStatus.AWAITING_REPLY.value,
        index=True,
    )
    replied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replied_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    appeal_status: Mapped[ReviewAppealStatus] = mapped_column(
        SQLEnum(
            ReviewAppealStatus,
            native_enum=False,
            length=30,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        default=ReviewAppealStatus.NONE,
        server_default=ReviewAppealStatus.NONE.value,
    )
    appeal_reason: Mapped[str | None] = mapped_column(Text)
    appealed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    sanatorium: Mapped["Sanatorium"] = relationship(back_populates="reviews")
    booking: Mapped["Booking | None"] = relationship()
    room: Mapped["Room | None"] = relationship()
    replied_by: Mapped["User | None"] = relationship(
        foreign_keys=[replied_by_user_id],
    )
