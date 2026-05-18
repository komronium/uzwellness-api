from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.room import Room


class RoomAvailability(Base):
    """Per-day exception row: only exists when a date has bookings or blocks.

    Default state (no row) means: 0 blocked, 0 booked, available =
    Room.inventory_count.
    """

    __tablename__ = "room_availability"

    __table_args__ = (
        UniqueConstraint("room_id", "date", name="uq_room_availability_date"),
        CheckConstraint(
            "units_blocked >= 0 AND units_booked >= 0",
            name="ck_room_availability_nonneg",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    room_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("rooms.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    units_blocked: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    units_booked: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    room: Mapped["Room"] = relationship(back_populates="availability")
