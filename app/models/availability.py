from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Integer, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.room import Room


class RoomAvailability(Base):
    __tablename__ = "room_availability"

    __table_args__ = (
        UniqueConstraint("room_id", "date", name="uq_room_availability_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    room_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("rooms.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    units_available: Mapped[int] = mapped_column(Integer, nullable=False)
    units_total: Mapped[int] = mapped_column(Integer, nullable=False)

    room: Mapped["Room"] = relationship(back_populates="availability")
