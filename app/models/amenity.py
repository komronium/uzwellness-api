from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Uuid,
    func,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.ids import uuid7

if TYPE_CHECKING:
    from app.models.program import TreatmentProgram
    from app.models.rate_plan import RatePlan
    from app.models.room import Room
    from app.models.sanatorium import Sanatorium


class AmenityCost(StrEnum):
    FREE = "free"
    PAID = "paid"  # "Additional charge"
    ON_REQUEST = "on_request"


class AmenityScope(StrEnum):
    SANATORIUM = "sanatorium"
    ROOM = "room"
    BOTH = "both"


class AmenitySelectionStatus(StrEnum):
    YES = "yes"
    NO = "no"
    NOT_SPECIFIED = "not_specified"


program_amenities = Table(
    "program_amenities",
    Base.metadata,
    Column(
        "program_id",
        Uuid,
        ForeignKey("treatment_programs.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "amenity_id",
        Uuid,
        ForeignKey("amenities.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

rate_plan_amenities = Table(
    "rate_plan_amenities",
    Base.metadata,
    Column(
        "rate_plan_id",
        Uuid,
        ForeignKey("rate_plans.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "amenity_id",
        Uuid,
        ForeignKey("amenities.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Amenity(Base):
    __tablename__ = "amenities"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    code: Mapped[str | None] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    description: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    category: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    scope: Mapped[AmenityScope] = mapped_column(
        SQLEnum(
            AmenityScope,
            native_enum=False,
            length=20,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=AmenityScope.BOTH,
        server_default=AmenityScope.BOTH.value,
        index=True,
    )
    icon: Mapped[str | None] = mapped_column(String(100))
    display_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    programs: Mapped[list["TreatmentProgram"]] = relationship(
        secondary=program_amenities, back_populates="amenities"
    )
    rate_plans: Mapped[list["RatePlan"]] = relationship(
        secondary=rate_plan_amenities, back_populates="amenities"
    )


class RoomAmenity(Base):
    __tablename__ = "room_amenities"

    room_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("rooms.id", ondelete="CASCADE"),
        primary_key=True,
    )
    amenity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("amenities.id", ondelete="CASCADE"),
        primary_key=True,
    )
    status: Mapped[AmenitySelectionStatus] = mapped_column(
        SQLEnum(
            AmenitySelectionStatus,
            native_enum=False,
            length=20,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=AmenitySelectionStatus.YES,
        server_default=AmenitySelectionStatus.YES.value,
    )
    cost: Mapped[AmenityCost] = mapped_column(
        SQLEnum(
            AmenityCost,
            native_enum=False,
            length=20,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=AmenityCost.FREE,
        server_default=AmenityCost.FREE.value,
    )
    is_available: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    details: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    display_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    amenity: Mapped["Amenity"] = relationship(lazy="selectin")
    room: Mapped["Room"] = relationship(back_populates="amenity_links")


class SanatoriumAmenity(Base):
    """Association object: a sanatorium offers an amenity, with cost + availability."""

    __tablename__ = "sanatorium_amenities"

    sanatorium_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("sanatoriums.id", ondelete="CASCADE"),
        primary_key=True,
    )
    amenity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("amenities.id", ondelete="CASCADE"),
        primary_key=True,
    )
    cost: Mapped[AmenityCost] = mapped_column(
        SQLEnum(
            AmenityCost,
            native_enum=False,
            length=20,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=AmenityCost.FREE,
        server_default="free",
    )
    is_available: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    status: Mapped[AmenitySelectionStatus] = mapped_column(
        SQLEnum(
            AmenitySelectionStatus,
            native_enum=False,
            length=20,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=AmenitySelectionStatus.YES,
        server_default=AmenitySelectionStatus.YES.value,
    )
    details: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    display_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    amenity: Mapped["Amenity"] = relationship(lazy="selectin")
    sanatorium: Mapped["Sanatorium"] = relationship(back_populates="amenity_links")
