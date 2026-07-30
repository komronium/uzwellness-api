from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Uuid,
    func,
    text,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.ids import uuid7
from app.models.base import TimestampMixin
from app.models.transfer_request import VehicleType


class TransferTariff(TimestampMixin, Base):
    """One immutable price version for a (route, vehicle type) pair.

    Rows are append-only: "editing" a price closes the current row
    (``effective_to = now()``) and inserts a new open one in the same
    transaction, so a booking's ``applied_tariff_id`` always points at the
    exact price the guest was charged. History is the rows ordered by
    ``effective_from`` desc; at most one open row exists per route+vehicle,
    enforced by ``uq_transfer_tariffs_current``.
    """

    __tablename__ = "transfer_tariffs"
    __table_args__ = (
        Index(
            "uq_transfer_tariffs_current",
            "route_from_id",
            "route_to_id",
            "vehicle_type",
            unique=True,
            postgresql_where=text("effective_to IS NULL"),
        ),
        Index("ix_transfer_tariffs_route", "route_from_id", "route_to_id"),
        CheckConstraint("price >= 0", name="ck_transfer_tariffs_price_non_negative"),
        CheckConstraint(
            "route_from_id <> route_to_id",
            name="ck_transfer_tariffs_distinct_endpoints",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="ck_transfer_tariffs_period_order",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    route_from_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("transfer_locations.id", ondelete="RESTRICT"), nullable=False
    )
    route_to_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("transfer_locations.id", ondelete="RESTRICT"), nullable=False
    )
    vehicle_type: Mapped[VehicleType] = mapped_column(
        SQLEnum(
            VehicleType,
            native_enum=False,
            length=20,
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
    )

    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)

    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def is_current(self) -> bool:
        return self.effective_to is None
