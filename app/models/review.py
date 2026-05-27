from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    SmallInteger,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.ids import uuid7

if TYPE_CHECKING:
    from app.models.sanatorium import Sanatorium


class SanatoriumReview(Base):
    __tablename__ = "sanatorium_reviews"

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
    reviewer_name: Mapped[str] = mapped_column(String(120), nullable=False)
    reviewer_country: Mapped[str | None] = mapped_column(String(60))
    traveler_type: Mapped[str | None] = mapped_column(String(30))
    rating: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    cleanliness: Mapped[int | None] = mapped_column(SmallInteger)
    amenities: Mapped[int | None] = mapped_column(SmallInteger)
    location: Mapped[int | None] = mapped_column(SmallInteger)
    service: Mapped[int | None] = mapped_column(SmallInteger)
    treatment: Mapped[int | None] = mapped_column(SmallInteger)
    value: Mapped[int | None] = mapped_column(SmallInteger)
    food: Mapped[int | None] = mapped_column(SmallInteger)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    sanatorium: Mapped["Sanatorium"] = relationship(back_populates="reviews")
