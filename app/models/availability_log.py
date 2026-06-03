from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, String, Uuid, func
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.ids import uuid7

if TYPE_CHECKING:
    from app.models.rate_plan import RatePlan
    from app.models.room import Room
    from app.models.sanatorium import Sanatorium
    from app.models.user import User


class AvailabilityLogCategory(StrEnum):
    ROOM_STATUS_RESTRICTIONS = "room_status_restrictions"
    INVENTORY = "inventory"
    RATE = "rate"
    MAX_ROOMS_AVAILABLE = "max_rooms_available"
    CANCELLATION_POLICY = "cancellation_policy"
    BULK_OPERATION = "bulk_operation"


class AvailabilityOperationLog(Base):
    __tablename__ = "availability_operation_logs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    sanatorium_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("sanatoriums.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    room_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("rooms.id", ondelete="SET NULL"), index=True
    )
    rate_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("rate_plans.id", ondelete="SET NULL"), index=True
    )
    operated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), index=True
    )

    category: Mapped[AvailabilityLogCategory] = mapped_column(
        SQLEnum(
            AvailabilityLogCategory,
            native_enum=False,
            length=40,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(40), nullable=False, default="api")

    check_in_from: Mapped[date | None] = mapped_column(Date, index=True)
    check_in_to: Mapped[date | None] = mapped_column(Date, index=True)
    weekdays: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    before: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    after: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    sanatorium: Mapped["Sanatorium"] = relationship()
    room: Mapped["Room | None"] = relationship()
    rate_plan: Mapped["RatePlan | None"] = relationship()
    operated_by: Mapped["User | None"] = relationship()
