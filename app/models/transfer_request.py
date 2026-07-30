from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin
from app.core.ids import uuid7


class TransferDirection(StrEnum):
    ARRIVAL = "arrival"  # airport → hotel
    DEPARTURE = "departure"  # hotel → airport
    ROUND_TRIP = "round_trip"  # both legs


class VehicleType(StrEnum):
    SEDAN = "sedan"
    MINIVAN = "minivan"
    BUS = "bus"


class TransferStatus(StrEnum):
    REQUESTED = "requested"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TransferPaymentState(StrEnum):
    INCLUDED = "included"  # priced inside the booking, settled with it
    UNPAID = "unpaid"  # added after checkout, settled offline
    PAID = "paid"  # operator marked the offline settlement received


class TransferRequest(TimestampMixin, Base):
    """Customer-requested transfer, coordinated by the transfer operator."""

    __tablename__ = "transfer_requests"
    __table_args__ = (
        CheckConstraint(
            "applied_price IS NULL OR applied_price >= 0",
            name="ck_transfer_requests_applied_price_non_negative",
        ),
        CheckConstraint(
            "commission_percent_snapshot IS NULL "
            "OR commission_percent_snapshot BETWEEN 0 AND 100",
            name="ck_transfer_requests_commission_percent_range",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    booking_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("bookings.id", ondelete="SET NULL"), index=True
    )

    direction: Mapped[TransferDirection] = mapped_column(
        SQLEnum(
            TransferDirection,
            native_enum=False,
            length=20,
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
    )

    # Denormalized snapshots of the route endpoint names at creation time; the
    # structured route lives in route_from_id / route_to_id.
    pickup_location: Mapped[str] = mapped_column(String(255), nullable=False)
    dropoff_location: Mapped[str] = mapped_column(String(255), nullable=False)

    route_from_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("transfer_locations.id", ondelete="SET NULL"), index=True
    )
    route_to_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("transfer_locations.id", ondelete="SET NULL"), index=True
    )
    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("transfer_vehicles.id", ondelete="SET NULL"), index=True
    )

    # Outbound (arrival) flight details — required for direction != departure.
    flight_number: Mapped[str | None] = mapped_column(String(20))
    flight_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Return leg — only used when direction = round_trip.
    return_flight_number: Mapped[str | None] = mapped_column(String(20))
    return_flight_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    passengers_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    vehicle_type: Mapped[VehicleType] = mapped_column(
        SQLEnum(
            VehicleType,
            native_enum=False,
            length=20,
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
        default=VehicleType.SEDAN,
    )

    # Legacy manual price, still settable by the operator on off-tariff jobs.
    price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str | None] = mapped_column(String(3))

    # Tariff-derived price, frozen when the transfer was added. Stored in the
    # booking's currency for `included` transfers so the single payment total
    # stays reconcilable even if the exchange rate moves later.
    applied_tariff_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("transfer_tariffs.id", ondelete="SET NULL"), index=True
    )
    applied_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    applied_currency: Mapped[str | None] = mapped_column(String(3))

    payment_state: Mapped[TransferPaymentState] = mapped_column(
        SQLEnum(
            TransferPaymentState,
            native_enum=False,
            length=20,
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
        default=TransferPaymentState.UNPAID,
        server_default=TransferPaymentState.UNPAID.value,
        index=True,
    )

    # Platform cut on this transfer, frozen from the transfer_admin's percent.
    commission_percent_snapshot: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    commission_amount_snapshot: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))

    status: Mapped[TransferStatus] = mapped_column(
        SQLEnum(
            TransferStatus,
            native_enum=False,
            length=20,
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
        default=TransferStatus.REQUESTED,
        index=True,
    )

    driver_name: Mapped[str | None] = mapped_column(String(255))
    driver_phone: Mapped[str | None] = mapped_column(String(32))

    notes: Mapped[str | None] = mapped_column(Text)
    admin_notes: Mapped[str | None] = mapped_column(Text)

    contact_phone: Mapped[str | None] = mapped_column(String(32))
