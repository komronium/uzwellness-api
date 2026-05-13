from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, SmallInteger, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.sanatorium import Sanatorium


class SanatoriumReview(Base):
    __tablename__ = "sanatorium_reviews"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    sanatorium_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("sanatoriums.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewer_name: Mapped[str] = mapped_column(String(120), nullable=False)
    reviewer_country: Mapped[str | None] = mapped_column(String(60))
    rating: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 1–5
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    sanatorium: Mapped["Sanatorium"] = relationship(back_populates="reviews")
