from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Uuid,
    func,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.ids import uuid7


class PackageItemType(StrEnum):
    FLIGHT = "flight"
    HOTEL = "hotel"
    TREATMENT = "treatment"
    TRANSFER = "transfer"
    MEAL = "meal"
    EXCURSION = "excursion"


class Package(Base):
    """Curated multi-day journey: flight + hotel + treatments + transfer + ...

    Sold as a single bundle priced per person. `sanatorium_id` is optional —
    multi-sanatorium tours are allowed.
    """

    __tablename__ = "packages"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    slug: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    title: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    description: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    hero_image_url: Mapped[str | None] = mapped_column(String(500))

    duration_nights: Mapped[int] = mapped_column(Integer, nullable=False)
    base_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)

    sanatorium_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("sanatoriums.id", ondelete="SET NULL"),
        index=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
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

    items: Mapped[list["PackageItem"]] = relationship(
        back_populates="package",
        cascade="all, delete-orphan",
        order_by="PackageItem.display_order, PackageItem.created_at",
    )


class PackageItem(Base):
    """A single line in a package (flight, hotel, transfer, ...).

    `is_included=True` → covered by `Package.base_price`.
    `is_included=False` + `extra_price` → optional add-on at extra cost.
    """

    __tablename__ = "package_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    package_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("packages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    item_type: Mapped[PackageItemType] = mapped_column(
        SQLEnum(
            PackageItemType,
            native_enum=False,
            length=20,
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
    )
    title: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    description: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )

    is_included: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    extra_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))

    display_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    package: Mapped[Package] = relationship(back_populates="items")
