from __future__ import annotations

import uuid

from app.core.ids import uuid7
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    String,
    Table,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.program import TreatmentProgram
    from app.models.sanatorium import Sanatorium

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

sanatorium_amenities = Table(
    "sanatorium_amenities",
    Base.metadata,
    Column(
        "sanatorium_id",
        Uuid,
        ForeignKey("sanatoriums.id", ondelete="CASCADE"),
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
