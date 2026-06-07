from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Numeric,
    String,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.ids import uuid7

if TYPE_CHECKING:
    from app.models.sanatorium import Sanatorium


class Destination(Base):
    """Marketing tile on the homepage.

    A destination is curated by super_admin and spans the set of
    sanatoriums tagged with its id. Examples: "Fergana Valley" → all
    sanatoriums across 3 viloyatlar; "Chimgan Mountains" → subset of
    Tashkent Region. Each sanatorium belongs to at most one destination
    (its featured tile); regions are independent.
    """

    __tablename__ = "destinations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    slug: Mapped[str] = mapped_column(
        String(120), unique=True, nullable=False, index=True
    )

    name: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    tagline: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    description: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )

    hero_image_url: Mapped[str | None] = mapped_column(String(500))
    lat: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    lng: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true", index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    sanatoriums: Mapped[list["Sanatorium"]] = relationship(back_populates="destination")
