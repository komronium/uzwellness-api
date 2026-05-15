from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Table,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.sanatorium import Sanatorium

program_amenities = Table(
    "program_amenities",
    Base.metadata,
    Column("program_id", Uuid, ForeignKey("treatment_programs.id", ondelete="CASCADE"), primary_key=True),
    Column("amenity_id", Uuid, ForeignKey("amenities.id", ondelete="CASCADE"), primary_key=True),
)

sanatorium_amenities = Table(
    "sanatorium_amenities",
    Base.metadata,
    Column("sanatorium_id", Uuid, ForeignKey("sanatoriums.id", ondelete="CASCADE"), primary_key=True),
    Column("amenity_id", Uuid, ForeignKey("amenities.id", ondelete="CASCADE"), primary_key=True),
)


class Amenity(Base):
    __tablename__ = "amenities"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    category: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    icon: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    programs: Mapped[list["TreatmentProgram"]] = relationship(
        secondary=program_amenities, back_populates="amenities"
    )
    sanatoriums: Mapped[list["Sanatorium"]] = relationship(
        secondary=sanatorium_amenities, back_populates="amenities"
    )


class TreatmentProgram(Base):
    __tablename__ = "treatment_programs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    sanatorium_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("sanatoriums.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    description: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )

    min_nights: Mapped[int | None] = mapped_column(Integer)
    max_nights: Mapped[int | None] = mapped_column(Integer)
    duration_minutes: Mapped[int | None] = mapped_column(Integer)

    price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str | None] = mapped_column(String(3))

    instructor_name: Mapped[str | None] = mapped_column(String(255))
    instructor_bio: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )

    group_size_min: Mapped[int | None] = mapped_column(Integer)
    group_size_max: Mapped[int | None] = mapped_column(Integer)

    what_to_bring: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    amenities: Mapped[list[Amenity]] = relationship(
        secondary=program_amenities, back_populates="programs"
    )
