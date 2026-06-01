from __future__ import annotations

import uuid
from datetime import datetime, time
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
    Time,
    Uuid,
    func,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.ids import uuid7

if TYPE_CHECKING:
    from app.models.amenity import SanatoriumAmenity
    from app.models.destination import Destination
    from app.models.region import Region
    from app.models.review import SanatoriumReview


class SanatoriumStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class PropertyType(StrEnum):
    SANATORIUM = "sanatorium"
    WELLNESS = "wellness"


class WellnessCategory(StrEnum):
    SPA_RESORT = "spa_resort"
    YOGA_RETREAT = "yoga_retreat"
    MEDITATION_CENTER = "meditation_center"
    FITNESS_RESORT = "fitness_resort"
    BEAUTY_SPA = "beauty_spa"
    DIGITAL_DETOX = "digital_detox"


class Sanatorium(Base):
    __tablename__ = "sanatoriums"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)

    name: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    slug: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    description: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    city: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    region_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("regions.id", ondelete="SET NULL"),
        index=True,
    )
    destination_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("destinations.id", ondelete="SET NULL"),
        index=True,
    )
    address: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    lat: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    lng: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))

    phones: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    website: Mapped[str | None] = mapped_column(String(255))

    check_in_time: Mapped[time | None] = mapped_column(Time)
    check_out_time: Mapped[time | None] = mapped_column(Time)

    pets_allowed: Mapped[bool | None] = mapped_column(Boolean)
    service_animals_allowed: Mapped[bool | None] = mapped_column(Boolean)
    min_checkin_age: Mapped[int | None] = mapped_column(SmallInteger)
    quiet_hours_from: Mapped[time | None] = mapped_column(Time)
    quiet_hours_to: Mapped[time | None] = mapped_column(Time)

    payment_methods: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    house_rules: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    cancellation_policy: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    reservation_auto_confirmation_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    reservation_fallback_processing_method: Mapped[str] = mapped_column(
        String(20), nullable=False, default="email", server_default="email"
    )
    reservation_fallback_contact_name: Mapped[str | None] = mapped_column(String(120))
    reservation_fallback_contact: Mapped[str | None] = mapped_column(String(255))
    weekly_schedule: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )

    stars: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    property_type: Mapped[PropertyType] = mapped_column(
        SQLEnum(
            PropertyType,
            native_enum=False,
            length=20,
            values_callable=lambda enum: [e.value for e in enum],
        ),
        default=PropertyType.SANATORIUM,
        nullable=False,
        index=True,
    )
    wellness_category: Mapped[WellnessCategory | None] = mapped_column(
        SQLEnum(
            WellnessCategory,
            native_enum=False,
            length=30,
            values_callable=lambda enum: [e.value for e in enum],
        ),
        index=True,
    )

    treatment_focuses: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    treatment_profile: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )

    year_opened: Mapped[int | None] = mapped_column(SmallInteger)
    languages_spoken: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    highlights: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    is_featured: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false", index=True
    )
    display_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0", index=True
    )
    promo_badges: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    surroundings: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    venues: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    meal_schedule: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    service_matrix: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    medical_base: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    policies: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )

    platform_commission_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    b2b_commission_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    agent_discount_tiers: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )

    avg_rating: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    review_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rating_breakdown: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )

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
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    region: Mapped["Region | None"] = relationship(lazy="selectin")
    destination: Mapped["Destination | None"] = relationship(
        back_populates="sanatoriums", lazy="selectin"
    )
    images: Mapped[list["SanatoriumImage"]] = relationship(
        back_populates="sanatorium",
        cascade="all, delete-orphan",
        order_by="SanatoriumImage.order",
    )
    amenity_links: Mapped[list["SanatoriumAmenity"]] = relationship(
        back_populates="sanatorium",
        cascade="all, delete-orphan",
    )
    reviews: Mapped[list["SanatoriumReview"]] = relationship(
        back_populates="sanatorium",
        cascade="all, delete-orphan",
        order_by="SanatoriumReview.created_at.desc()",
    )


class SanatoriumImage(Base):
    __tablename__ = "sanatorium_images"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    sanatorium_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("sanatoriums.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    url: Mapped[str] = mapped_column(String(500), nullable=False)
    order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_360: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    category: Mapped[str | None] = mapped_column(String(40))
    caption: Mapped[str | None] = mapped_column(String(255))
    caption_i18n: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    alt_text: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    tags: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    sanatorium: Mapped[Sanatorium] = relationship(back_populates="images")
