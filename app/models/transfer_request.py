from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.ids import uuid7


class TransferDirection(StrEnum):
    ARRIVAL = "arrival"        # airport → hotel
    DEPARTURE = "departure"    # hotel → airport
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


class TransferRequest(Base):
    """Customer-requested airport transfer, coordinated by super_admin."""

    __tablename__ = "transfer_requests"

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

    pickup_location: Mapped[str] = mapped_column(String(255), nullable=False)
    dropoff_location: Mapped[str] = mapped_column(String(255), nullable=False)

    # Outbound (arrival) flight details — required for direction != departure.
    flight_number: Mapped[str | None] = mapped_column(String(20))
    flight_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Return leg — only used when direction = round_trip.
    return_flight_number: Mapped[str | None] = mapped_column(String(20))
    return_flight_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

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

    price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str | None] = mapped_column(String(3))

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

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
