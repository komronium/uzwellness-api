from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Index,
    Date,
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
from app.models.base import TimestampMixin
from app.core.ids import uuid7
from app.models.amenity import RoomAmenity

if TYPE_CHECKING:
    from app.models.amenity import Amenity
    from app.models.availability import RoomAvailability
    from app.models.rate_plan import RatePlan


class RoomView(StrEnum):
    CITY = "city"
    SEA = "sea"
    GARDEN = "garden"
    MOUNTAIN = "mountain"
    POOL = "pool"
    LAKE = "lake"
    PARK = "park"
    COURTYARD = "courtyard"
    STREET = "street"
    LANDMARK = "landmark"


class AccommodationType(StrEnum):
    HOTEL_ROOM = "hotel_room"
    SHARED_ROOM_BED = "shared_room_bed"


class GenderRestriction(StrEnum):
    MALE_ONLY = "male_only"
    FEMALE_ONLY = "female_only"


class RoomSizePolicy(StrEnum):
    SAME_SIZE = "same_size"
    DIFFERENT_SIZES = "different_sizes"


class SmokingPolicy(StrEnum):
    NON_SMOKING = "non_smoking"
    SMOKING_PERMITTED = "smoking_permitted"
    SOME_SMOKING = "some_smoking"


class WindowPolicy(StrEnum):
    ALL_ROOMS_HAVE_WINDOWS = "all_rooms_have_windows"
    SOME_ROOMS_HAVE_WINDOWS = "some_rooms_have_windows"
    NO_ROOMS_HAVE_WINDOWS = "no_rooms_have_windows"


class Room(TimestampMixin, Base):
    __tablename__ = "rooms"
    __table_args__ = (
        Index("ix_rooms_search_available", "sanatorium_id", "is_active", "base_price"),
        CheckConstraint("capacity > 0", name="ck_rooms_capacity_positive"),
        CheckConstraint(
            "inventory_count >= 0", name="ck_rooms_inventory_count_non_negative"
        ),
        CheckConstraint("base_price >= 0", name="ck_rooms_base_price_non_negative"),
        CheckConstraint(
            "base_price_weekend IS NULL OR base_price_weekend >= 0",
            name="ck_rooms_base_price_weekend_non_negative",
        ),
        CheckConstraint(
            "markup_percent >= 0", name="ck_rooms_markup_percent_non_negative"
        ),
        CheckConstraint(
            "discount_percent IS NULL OR discount_percent BETWEEN 0 AND 100",
            name="ck_rooms_discount_percent_range",
        ),
        CheckConstraint("min_nights > 0", name="ck_rooms_min_nights_positive"),
        CheckConstraint(
            "size_sqm IS NULL OR size_sqm > 0", name="ck_rooms_size_sqm_positive"
        ),
        CheckConstraint(
            "max_adults IS NULL OR max_adults >= 0",
            name="ck_rooms_max_adults_non_negative",
        ),
        CheckConstraint(
            "max_children IS NULL OR max_children >= 0",
            name="ck_rooms_max_children_non_negative",
        ),
        CheckConstraint(
            "max_child_rate_children IS NULL OR max_child_rate_children >= 0",
            name="ck_rooms_max_child_rate_children_non_negative",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    sanatorium_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("sanatoriums.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    description: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )

    size_sqm: Mapped[int | None] = mapped_column(Integer)
    room_size_policy: Mapped[RoomSizePolicy] = mapped_column(
        SQLEnum(
            RoomSizePolicy,
            native_enum=False,
            length=30,
            values_callable=lambda enum: [e.value for e in enum],
        ),
        nullable=False,
        default=RoomSizePolicy.SAME_SIZE,
        server_default=RoomSizePolicy.SAME_SIZE.value,
    )
    floor: Mapped[str | None] = mapped_column(String(20))
    beds: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    view: Mapped[RoomView | None] = mapped_column(
        SQLEnum(
            RoomView,
            native_enum=False,
            length=20,
            values_callable=lambda enum: [e.value for e in enum],
        )
    )
    smoking_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    smoking_policy: Mapped[SmokingPolicy] = mapped_column(
        SQLEnum(
            SmokingPolicy,
            native_enum=False,
            length=30,
            values_callable=lambda enum: [e.value for e in enum],
        ),
        nullable=False,
        default=SmokingPolicy.NON_SMOKING,
        server_default=SmokingPolicy.NON_SMOKING.value,
    )
    window_policy: Mapped[WindowPolicy | None] = mapped_column(
        SQLEnum(
            WindowPolicy,
            native_enum=False,
            length=40,
            values_callable=lambda enum: [e.value for e in enum],
        )
    )
    window_description: Mapped[str | None] = mapped_column(String(255))
    room_features: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )

    accommodation_type: Mapped[AccommodationType] = mapped_column(
        SQLEnum(
            AccommodationType,
            native_enum=False,
            length=30,
            values_callable=lambda enum: [e.value for e in enum],
        ),
        nullable=False,
        default=AccommodationType.HOTEL_ROOM,
        server_default=AccommodationType.HOTEL_ROOM.value,
    )
    gender_restriction: Mapped[GenderRestriction | None] = mapped_column(
        SQLEnum(
            GenderRestriction,
            native_enum=False,
            length=20,
            values_callable=lambda enum: [e.value for e in enum],
        )
    )
    capacity: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    max_adults: Mapped[int | None] = mapped_column(SmallInteger)
    max_children: Mapped[int | None] = mapped_column(SmallInteger)
    max_child_rate_children: Mapped[int | None] = mapped_column(SmallInteger)
    inventory_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    room_advisories: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    base_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    base_price_weekend: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    markup_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("0")
    )
    discount_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    min_nights: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    display_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    availability: Mapped[list["RoomAvailability"]] = relationship(
        back_populates="room",
        cascade="all, delete-orphan",
    )
    price_periods: Mapped[list["RoomPricePeriod"]] = relationship(
        back_populates="room",
        cascade="all, delete-orphan",
        order_by="RoomPricePeriod.date_from",
    )
    images: Mapped[list["RoomImage"]] = relationship(
        back_populates="room",
        cascade="all, delete-orphan",
        order_by="RoomImage.order",
        lazy="selectin",
    )
    rate_plans: Mapped[list["RatePlan"]] = relationship(
        back_populates="room",
        cascade="all, delete-orphan",
        order_by="RatePlan.created_at",
    )
    amenity_links: Mapped[list["RoomAmenity"]] = relationship(
        back_populates="room",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    amenities: Mapped[list["Amenity"]] = relationship(
        secondary="room_amenities",
        viewonly=True,
        lazy="selectin",
    )


class RoomPricePeriod(Base):
    __tablename__ = "room_price_periods"
    __table_args__ = (
        CheckConstraint(
            "date_to >= date_from", name="ck_room_price_periods_date_order"
        ),
        CheckConstraint(
            "base_price >= 0", name="ck_room_price_periods_base_price_non_negative"
        ),
        CheckConstraint(
            "base_price_weekend IS NULL OR base_price_weekend >= 0",
            name="ck_room_price_periods_base_price_weekend_non_negative",
        ),
        CheckConstraint(
            "discount_percent IS NULL OR discount_percent BETWEEN 0 AND 100",
            name="ck_room_price_periods_discount_percent_range",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    room_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("rooms.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    label: Mapped[str | None] = mapped_column(String(120))
    date_from: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    date_to: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    base_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    base_price_weekend: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    discount_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    room: Mapped["Room"] = relationship(back_populates="price_periods")


class RoomImage(Base):
    __tablename__ = "room_images"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    room_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("rooms.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    url: Mapped[str] = mapped_column(String(500), nullable=False)
    order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_video: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
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

    room: Mapped["Room"] = relationship(back_populates="images")
