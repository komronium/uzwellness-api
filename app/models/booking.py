from __future__ import annotations

import secrets
import string
import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Index,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Uuid,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin
from app.core.ids import uuid7
from app.models.rate_plan import BoardType, ConfirmationType, PaymentTiming

if TYPE_CHECKING:
    from app.models.extra_bed import BookingExtraBed
    from app.models.notification import Notification
    from app.models.payment import Payment
    from app.models.user import User

_ALPHABET = string.ascii_uppercase + string.digits
_TASHKENT_TZ = ZoneInfo("Asia/Tashkent")


def _generate_code() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(8))


class BookingStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class BookingType(StrEnum):
    ROOM = "room"
    SESSION = "session"
    PACKAGE = "package"


def generate_reservation_number(
    *,
    booking_type: BookingType | str | None = None,
    is_b2b: bool = False,
    created_at: datetime | None = None,
) -> str:
    """Customer-facing 16-digit reservation number.

    Format: YYMMDDTCXXXXXXXX
      YYMMDD   booking creation date in Asia/Tashkent
      T        booking type: 1 room, 2 treatment/session, 3 package, 0 unknown
      C        channel: 1 customer/direct, 2 B2B agent
      XXXXXXXX random digits, not sequential
    """

    created_at = created_at or datetime.now(_TASHKENT_TZ)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=_TASHKENT_TZ)
    date_part = created_at.astimezone(_TASHKENT_TZ).strftime("%y%m%d")
    type_digit = _booking_type_digit(booking_type)
    channel_digit = "2" if is_b2b else "1"
    random_part = f"{secrets.randbelow(10**8):08d}"
    return f"{date_part}{type_digit}{channel_digit}{random_part}"


def _generate_reservation_number() -> str:
    return generate_reservation_number()


def _booking_type_digit(booking_type: BookingType | str | None) -> str:
    value = (
        booking_type.value if isinstance(booking_type, BookingType) else booking_type
    )
    return {
        BookingType.ROOM.value: "1",
        BookingType.SESSION.value: "2",
        BookingType.PACKAGE.value: "3",
    }.get(value or "", "0")


class Booking(TimestampMixin, Base):
    __tablename__ = "bookings"
    __table_args__ = (
        Index("ix_bookings_user_created", "user_id", "created_at"),
        CheckConstraint(
            "(booking_type = 'session' AND check_out >= check_in) "
            "OR (booking_type <> 'session' AND check_out > check_in)",
            name="ck_bookings_date_order",
        ),
        CheckConstraint("guests > 0", name="ck_bookings_guests_positive"),
        CheckConstraint(
            "adults IS NULL OR adults >= 0", name="ck_bookings_adults_non_negative"
        ),
        CheckConstraint(
            "children IS NULL OR children >= 0",
            name="ck_bookings_children_non_negative",
        ),
        CheckConstraint("rooms_count > 0", name="ck_bookings_rooms_count_positive"),
        CheckConstraint(
            "final_price >= 0", name="ck_bookings_final_price_non_negative"
        ),
        CheckConstraint(
            "original_price IS NULL OR original_price >= 0",
            name="ck_bookings_original_price_non_negative",
        ),
        CheckConstraint(
            "commission_snapshot IS NULL OR commission_snapshot >= 0",
            name="ck_bookings_commission_non_negative",
        ),
        CheckConstraint(
            "commission_percent_snapshot IS NULL "
            "OR commission_percent_snapshot BETWEEN 0 AND 100",
            name="ck_bookings_commission_percent_range",
        ),
        CheckConstraint(
            "agent_discount_percent_snapshot IS NULL "
            "OR agent_discount_percent_snapshot BETWEEN 0 AND 100",
            name="ck_bookings_agent_discount_percent_range",
        ),
        CheckConstraint(
            "free_cancellation_days IS NULL OR free_cancellation_days >= 0",
            name="ck_bookings_free_cancellation_days_non_negative",
        ),
        CheckConstraint(
            "cancellation_penalty_percent IS NULL "
            "OR cancellation_penalty_percent BETWEEN 0 AND 100",
            name="ck_bookings_cancellation_penalty_percent_range",
        ),
        CheckConstraint(
            "cancellation_penalty_amount IS NULL OR cancellation_penalty_amount >= 0",
            name="ck_bookings_cancellation_penalty_amount_non_negative",
        ),
        CheckConstraint(
            "promo_percent_snapshot IS NULL OR promo_percent_snapshot BETWEEN 0 AND 100",
            name="ck_bookings_promo_percent_range",
        ),
        CheckConstraint(
            "board_guests IS NULL OR board_guests > 0",
            name="ck_bookings_board_guests_positive",
        ),
    )

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
    adults: Mapped[int | None] = mapped_column(Integer)
    children: Mapped[int | None] = mapped_column(Integer)
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
    room_distribution: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    treatment_selections: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    guest_options: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    offer_snapshot: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
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
