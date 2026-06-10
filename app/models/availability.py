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
from app.core.ids import uuid7

if TYPE_CHECKING:
    from app.models.room import Room


class RoomAvailability(Base):
    __tablename__ = "room_availability"
    __table_args__ = (
        UniqueConstraint("room_id", "date", name="uq_room_availability_date"),
        CheckConstraint(
            "units_blocked >= 0", name="ck_room_availability_units_blocked_non_negative"
        ),
        CheckConstraint(
            "units_booked >= 0", name="ck_room_availability_units_booked_non_negative"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
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
