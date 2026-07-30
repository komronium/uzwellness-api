from __future__ import annotations

import uuid

from sqlalchemy import Boolean, CheckConstraint, Integer, String, Uuid
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.ids import uuid7
from app.models.base import TimestampMixin
from app.models.transfer_request import VehicleType


class TransferVehicle(TimestampMixin, Base):
    """A car in the transfer operator's fleet, assigned to a transfer request."""

    __tablename__ = "transfer_vehicles"
    __table_args__ = (
        CheckConstraint("capacity > 0", name="ck_transfer_vehicles_capacity_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    vehicle_type: Mapped[VehicleType] = mapped_column(
        SQLEnum(
            VehicleType,
            native_enum=False,
            length=20,
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
        index=True,
    )
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    plate: Mapped[str] = mapped_column(
        String(32), nullable=False, unique=True, index=True
    )
    label: Mapped[str | None] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true", index=True
    )
