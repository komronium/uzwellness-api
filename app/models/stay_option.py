from __future__ import annotations

import uuid
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin
from app.core.ids import uuid7
from app.models.rate_plan import BoardType


class StayOptionGuestType(StrEnum):
    ADULT = "adult"
    CHILD = "child"


def _enum(enum_cls: type[StrEnum], length: int) -> SQLEnum:
    return SQLEnum(
        enum_cls,
        native_enum=False,
        length=length,
        values_callable=lambda e: [m.value for m in e],
    )


class SanatoriumStayOptionPrice(TimestampMixin, Base):
    __tablename__ = "sanatorium_stay_option_prices"
    __table_args__ = (
        UniqueConstraint(
            "sanatorium_id",
            "guest_type",
            "board",
            "treatment_included",
            name="uq_sanatorium_stay_option_price",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    sanatorium_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("sanatoriums.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    guest_type: Mapped[StayOptionGuestType] = mapped_column(
        _enum(StayOptionGuestType, 20), nullable=False
    )
    board: Mapped[BoardType] = mapped_column(_enum(BoardType, 20), nullable=False)
    treatment_included: Mapped[bool] = mapped_column(Boolean, nullable=False)
    price_delta: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="UZS")
    is_available: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
