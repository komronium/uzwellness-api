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
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.ids import uuid7

if TYPE_CHECKING:
    from app.models.amenity import Amenity
    from app.models.room import Room

from app.models.amenity import rate_plan_amenities


class BoardType(StrEnum):
    ROOM_ONLY = "room_only"
    BREAKFAST = "breakfast"
    HALF_BOARD = "half_board"
    FULL_BOARD = "full_board"
    ALL_INCLUSIVE = "all_inclusive"


class PaymentTiming(StrEnum):
    PREPAY = "prepay"
    AT_HOTEL = "at_hotel"
    DEPOSIT = "deposit"


class ConfirmationType(StrEnum):
    INSTANT = "instant"
    ON_REQUEST = "on_request"


def _enum(enum_cls: type[StrEnum], length: int) -> SQLEnum:
    return SQLEnum(
        enum_cls,
        native_enum=False,
        length=length,
        values_callable=lambda e: [m.value for m in e],
    )


class RatePlan(Base):
    __tablename__ = "rate_plans"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    room_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("rooms.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    board: Mapped[BoardType] = mapped_column(
        _enum(BoardType, 20), nullable=False, default=BoardType.ROOM_ONLY
    )
    # board_optional: meals are a paid add-on (board_price) instead of bundled.
    board_optional: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    board_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    # Number of guests the meal plan covers, e.g. "breakfast for 2 guests".
    board_guests: Mapped[int | None] = mapped_column(Integer)

    refundable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    free_cancellation_days: Mapped[int | None] = mapped_column(Integer)
    cancellation_penalty_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    cancellation_penalty_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))

    payment_timing: Mapped[PaymentTiming] = mapped_column(
        _enum(PaymentTiming, 20), nullable=False, default=PaymentTiming.PREPAY
    )
    confirmation: Mapped[ConfirmationType] = mapped_column(
        _enum(ConfirmationType, 20), nullable=False, default=ConfirmationType.INSTANT
    )

    # Adjustment applied to the room stay total, e.g. -10 for a non-refundable rate.
    price_adjustment_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))

    # Time-boxed promotional discount, distinct from the standing adjustment above.
    promo_label: Mapped[str | None] = mapped_column(String(60))
    promo_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    promo_starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    promo_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    min_nights: Mapped[int | None] = mapped_column(Integer)
    max_nights: Mapped[int | None] = mapped_column(Integer)

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
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

    room: Mapped["Room"] = relationship(back_populates="rate_plans")
    amenities: Mapped[list["Amenity"]] = relationship(
        secondary=rate_plan_amenities,
        back_populates="rate_plans",
        lazy="selectin",
    )
    date_rules: Mapped[list["RatePlanDateRule"]] = relationship(
        back_populates="rate_plan",
        cascade="all, delete-orphan",
        order_by="RatePlanDateRule.date",
    )


class RatePlanDateRule(Base):
    __tablename__ = "rate_plan_date_rules"
    __table_args__ = (
        UniqueConstraint("rate_plan_id", "date", name="uq_rate_plan_date_rule"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    rate_plan_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("rate_plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    selling_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    is_closed: Mapped[bool | None] = mapped_column(Boolean)
    min_advance_hours: Mapped[int | None] = mapped_column(Integer)
    max_advance_hours: Mapped[int | None] = mapped_column(Integer)
    min_stay_nights: Mapped[int | None] = mapped_column(Integer)
    min_stay_arrival_nights: Mapped[int | None] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    rate_plan: Mapped["RatePlan"] = relationship(back_populates="date_rules")
