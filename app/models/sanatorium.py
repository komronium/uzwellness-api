from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Uuid,
    func,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.amenity import sanatorium_amenities

if TYPE_CHECKING:
    from app.models.amenity import Amenity
    from app.models.review import SanatoriumReview


class SanatoriumStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class Sanatorium(Base):
    __tablename__ = "sanatoriums"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    description: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    city: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    address: Mapped[str] = mapped_column(String(500), nullable=False)
    lat: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    lng: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    phone: Mapped[str | None] = mapped_column(String(30))

    stars: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    # High-level medical/treatment categories (e.g. ["cardiovascular", "digestive"])
    treatment_focuses: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    # Denormalized for fast listing queries — updated by ReviewService
    avg_rating: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    review_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    status: Mapped[SanatoriumStatus] = mapped_column(
        SQLEnum(
            SanatoriumStatus,
            native_enum=False,
            length=20,
            values_callable=lambda enum: [e.value for e in enum],
        ),
        default=SanatoriumStatus.PENDING,
        nullable=False,
        index=True,
    )

    admin_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    images: Mapped[list["SanatoriumImage"]] = relationship(
        back_populates="sanatorium",
        cascade="all, delete-orphan",
        order_by="SanatoriumImage.order",
    )
    amenities: Mapped[list["Amenity"]] = relationship(
        secondary=sanatorium_amenities, back_populates="sanatoriums"
    )
    reviews: Mapped[list["SanatoriumReview"]] = relationship(
        back_populates="sanatorium",
        cascade="all, delete-orphan",
        order_by="SanatoriumReview.created_at.desc()",
    )


class SanatoriumImage(Base):
    __tablename__ = "sanatorium_images"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    sanatorium_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("sanatoriums.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    url: Mapped[str] = mapped_column(String(500), nullable=False)
    order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    caption: Mapped[str | None] = mapped_column(String(255))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    sanatorium: Mapped[Sanatorium] = relationship(back_populates="images")
