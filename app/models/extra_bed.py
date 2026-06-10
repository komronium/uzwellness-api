from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.ids import uuid7

if TYPE_CHECKING:
    from app.models.booking import Booking


class ExtraBedConfig(Base):
    __tablename__ = "extra_bed_configs"
    __table_args__ = (
        CheckConstraint(
            "price_per_night >= 0",
            name="ck_extra_bed_configs_price_per_night_non_negative",
        ),
        CheckConstraint(
            "max_count > 0", name="ck_extra_bed_configs_max_count_positive"
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
    price_per_night: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    max_count: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    bed_bookings: Mapped[list["BookingExtraBed"]] = relationship(
        back_populates="config"
    )


class BookingExtraBed(Base):
    __tablename__ = "booking_extra_beds"
    __table_args__ = (
        CheckConstraint(
            "price_per_night_snapshot >= 0",
            name="ck_booking_extra_beds_price_per_night_non_negative",
        ),
        CheckConstraint("count > 0", name="ck_booking_extra_beds_count_positive"),
        CheckConstraint(
            "total_price >= 0", name="ck_booking_extra_beds_total_price_non_negative"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    booking_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    config_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("extra_bed_configs.id", ondelete="SET NULL")
    )
    name_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    price_per_night_snapshot: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False)
    total_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    booking: Mapped["Booking"] = relationship(back_populates="extra_beds")
    config: Mapped[ExtraBedConfig | None] = relationship(back_populates="bed_bookings")
