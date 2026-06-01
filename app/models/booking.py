from __future__ import annotations

import secrets
import string
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
    Uuid,
    func,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.ids import uuid7
from app.models.rate_plan import BoardType, ConfirmationType, PaymentTiming

if TYPE_CHECKING:
    from app.models.extra_bed import BookingExtraBed
    from app.models.notification import Notification
    from app.models.payment import Payment
    from app.models.user import User

_ALPHABET = string.ascii_uppercase + string.digits


def _generate_code() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(8))


def _generate_reservation_number() -> str:
    return f"{secrets.randbelow(10**16):016d}"


class BookingStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class BookingType(StrEnum):
    ROOM = "room"
    SESSION = "session"
    PACKAGE = "package"


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    code: Mapped[str] = mapped_column(
        String(16), unique=True, nullable=False, index=True, default=_generate_code
    )
    reservation_number: Mapped[str] = mapped_column(
        String(24),
        unique=True,
        nullable=False,
        index=True,
        default=_generate_reservation_number,
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    room_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("rooms.id", ondelete="SET NULL"), index=True
    )
    program_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("treatment_programs.id", ondelete="SET NULL"), index=True
    )
    package_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("packages.id", ondelete="SET NULL"), index=True
    )
    rate_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("rate_plans.id", ondelete="SET NULL"), index=True
    )

    booking_type: Mapped["BookingType"] = mapped_column(
        SQLEnum(
            BookingType,
            native_enum=False,
            length=20,
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
        default=BookingType.ROOM,
        index=True,
    )

    check_in: Mapped[date] = mapped_column(Date, nullable=False)
    check_out: Mapped[date] = mapped_column(Date, nullable=False)
    guests: Mapped[int] = mapped_column(Integer, nullable=False)
    rooms_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )

    status: Mapped[BookingStatus] = mapped_column(
        SQLEnum(
            BookingStatus,
            native_enum=False,
            length=20,
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
        default=BookingStatus.PENDING,
        index=True,
    )

    final_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)

    is_b2b: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    guest_details: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    special_requests: Mapped[str | None] = mapped_column(String(1000))

    commission_snapshot: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    commission_percent_snapshot: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    agent_discount_percent_snapshot: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2)
    )

    # Rate-plan terms frozen at booking time (room bookings only).
    board: Mapped[BoardType | None] = mapped_column(
        SQLEnum(
            BoardType,
            native_enum=False,
            length=20,
            values_callable=lambda e: [x.value for x in e],
        )
    )
    refundable: Mapped[bool | None] = mapped_column(Boolean)
    free_cancellation_days: Mapped[int | None] = mapped_column(Integer)
    cancellation_penalty_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    cancellation_penalty_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    # Price before a time-boxed promo (strikethrough), when a promo applied.
    original_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    promo_percent_snapshot: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    payment_timing: Mapped[PaymentTiming | None] = mapped_column(
        SQLEnum(
            PaymentTiming,
            native_enum=False,
            length=20,
            values_callable=lambda e: [x.value for x in e],
        )
    )
    confirmation: Mapped[ConfirmationType | None] = mapped_column(
        SQLEnum(
            ConfirmationType,
            native_enum=False,
            length=20,
            values_callable=lambda e: [x.value for x in e],
        )
    )
    rate_plan_name: Mapped[dict | None] = mapped_column(JSONB)
    board_guests: Mapped[int | None] = mapped_column(Integer)

    is_processed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false", index=True
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), index=True
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

    notifications: Mapped[list["Notification"]] = relationship(
        back_populates="booking", cascade="all, delete-orphan"
    )
    extra_beds: Mapped[list["BookingExtraBed"]] = relationship(
        back_populates="booking", cascade="all, delete-orphan"
    )
    user: Mapped["User | None"] = relationship(foreign_keys=[user_id], lazy="raise")
    payments: Mapped[list["Payment"]] = relationship(
        primaryjoin="Booking.id == Payment.booking_id",
        order_by="Payment.created_at.desc()",
        lazy="raise",
        viewonly=True,
    )
