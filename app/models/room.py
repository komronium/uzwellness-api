from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.availability import RoomAvailability


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    sanatorium_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("sanatoriums.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    room_amenities: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    capacity: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    base_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    base_price_weekend: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    markup_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("0")
    )
    discount_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    b2b_discount_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
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


class RoomPricePeriod(Base):
    __tablename__ = "room_price_periods"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
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
