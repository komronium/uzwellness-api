import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Uuid,
    func,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.ids import uuid7


class PaymentMethod(StrEnum):
    PAYME = "payme"
    CLICK = "click"
    CASH = "cash"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REFUND_PENDING = "refund_pending"
    REFUNDED = "refunded"


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_payments_amount_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    booking_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    method: Mapped[PaymentMethod] = mapped_column(
        SQLEnum(
            PaymentMethod,
            native_enum=False,
            length=20,
            values_callable=lambda enum: [e.value for e in enum],
        ),
        nullable=False,
    )
    status: Mapped[PaymentStatus] = mapped_column(
        SQLEnum(
            PaymentStatus,
            native_enum=False,
            length=20,
            values_callable=lambda enum: [e.value for e in enum],
        ),
        nullable=False,
        default=PaymentStatus.PENDING,
        index=True,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    merchant_trans_id: Mapped[str | None] = mapped_column(String(64), index=True)
    provider_payment_id: Mapped[str | None] = mapped_column(String(120), index=True)
    raw_payload: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
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
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
