from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
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
from app.core.ids import uuid7
from app.models.amenity import room_amenities

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


class Room(Base):
    __tablename__ = "rooms"

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

    capacity: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    max_adults: Mapped[int | None] = mapped_column(SmallInteger)
    max_children: Mapped[int | None] = mapped_column(SmallInteger)
    inventory_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    base_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    base_price_weekend: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    markup_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("0")
    )
    discount_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    min_nights: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

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
    amenities: Mapped[list["Amenity"]] = relationship(
        secondary=room_amenities, lazy="selectin"
    )


class RoomPricePeriod(Base):
    __tablename__ = "room_price_periods"

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
    caption: Mapped[str | None] = mapped_column(String(255))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    room: Mapped["Room"] = relationship(back_populates="images")
