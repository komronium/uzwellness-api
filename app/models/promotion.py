from __future__ import annotations

import uuid
from datetime import date, datetime, time
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    Table,
    Time,
    Uuid,
    func,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.ids import uuid7

if TYPE_CHECKING:
    from app.models.rate_plan import RatePlan
    from app.models.sanatorium import Sanatorium


class PromotionCategory(StrEnum):
    MOBILE_RATE = "mobile_rate"
    BASIC_DEAL = "basic_deal"
    EARLY_BIRD = "early_bird"
    LAST_MINUTE = "last_minute"
    LONG_STAY = "long_stay"
    SEASONAL = "seasonal"
    MEMBER = "member"
    PACKAGE = "package"
    CUSTOM = "custom"


class PromotionStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    INACTIVE = "inactive"


class PromotionAudience(StrEnum):
    ALL_GUESTS = "all_guests"


class PromotionCancellationPolicyMode(StrEnum):
    ORIGINAL = "original"
    CUSTOM = "custom"


promotion_rate_plans = Table(
    "promotion_rate_plans",
    Base.metadata,
    Column(
        "promotion_id",
        Uuid,
        ForeignKey("promotions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "rate_plan_id",
        Uuid,
        ForeignKey("rate_plans.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


def _enum(enum_cls: type[StrEnum], length: int) -> SQLEnum:
    return SQLEnum(
        enum_cls,
        native_enum=False,
        length=length,
        values_callable=lambda enum: [item.value for item in enum],
    )


class Promotion(Base):
    __tablename__ = "promotions"
    __table_args__ = (
        CheckConstraint(
            "discount_percent BETWEEN 0 AND 100",
            name="ck_promotions_discount_percent_range",
        ),
        CheckConstraint(
            "booking_date_to IS NULL OR booking_date_from IS NULL "
            "OR booking_date_to >= booking_date_from",
            name="ck_promotions_booking_date_order",
        ),
        CheckConstraint(
            "stay_date_to IS NULL OR stay_date_from IS NULL "
            "OR stay_date_to >= stay_date_from",
            name="ck_promotions_stay_date_order",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    sanatorium_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("sanatoriums.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    category: Mapped[PromotionCategory] = mapped_column(
        _enum(PromotionCategory, 30), nullable=False, index=True
    )
    status: Mapped[PromotionStatus] = mapped_column(
        _enum(PromotionStatus, 20),
        nullable=False,
        default=PromotionStatus.ACTIVE,
        server_default=PromotionStatus.ACTIVE.value,
        index=True,
    )
    discount_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)

    booking_date_from: Mapped[date | None] = mapped_column(Date, index=True)
    booking_date_to: Mapped[date | None] = mapped_column(Date, index=True)
    stay_date_from: Mapped[date | None] = mapped_column(Date, index=True)
    stay_date_to: Mapped[date | None] = mapped_column(Date, index=True)
    booking_weekdays: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    stay_weekdays: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    booking_time_from: Mapped[time | None] = mapped_column(Time)
    booking_time_to: Mapped[time | None] = mapped_column(Time)

    audience: Mapped[PromotionAudience] = mapped_column(
        _enum(PromotionAudience, 30),
        nullable=False,
        default=PromotionAudience.ALL_GUESTS,
        server_default=PromotionAudience.ALL_GUESTS.value,
    )
    cancellation_policy_mode: Mapped[PromotionCancellationPolicyMode] = mapped_column(
        _enum(PromotionCancellationPolicyMode, 20),
        nullable=False,
        default=PromotionCancellationPolicyMode.ORIGINAL,
        server_default=PromotionCancellationPolicyMode.ORIGINAL.value,
    )
    custom_cancellation_policy: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    pay_with_cost_per_sale_account: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
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

    sanatorium: Mapped["Sanatorium"] = relationship()
    rate_plans: Mapped[list["RatePlan"]] = relationship(
        secondary=promotion_rate_plans,
        lazy="selectin",
    )
