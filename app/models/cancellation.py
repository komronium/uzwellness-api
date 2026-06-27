from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.ids import uuid7
from app.models.base import TimestampMixin


class CancellationStatus(StrEnum):
    CODE_SENT = "code_sent"  # code emailed to the customer, awaiting confirmation
    AWAITING_APPROVAL = "awaiting_approval"  # confirmed; admin must approve the refund
    APPROVED = "approved"  # admin approved; booking cancelled + refund queued
    REJECTED = "rejected"  # admin declined; booking stays active
    EXPIRED = "expired"  # code expired before confirmation
    SUPERSEDED = "superseded"  # replaced by a newer request


class CancellationRequest(TimestampMixin, Base):
    """A customer-initiated, email-code-verified request to cancel a booking.

    The customer requests a code (emailed to them), confirms it, and the request
    then awaits admin approval before the booking is actually cancelled and the
    refund is queued.
    """

    __tablename__ = "cancellation_requests"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    booking_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # SHA-256 of the numeric code; the plaintext code is never stored.
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    status: Mapped[CancellationStatus] = mapped_column(
        SQLEnum(
            CancellationStatus,
            native_enum=False,
            length=20,
            values_callable=lambda enum: [e.value for e in enum],
        ),
        nullable=False,
        default=CancellationStatus.CODE_SENT,
        index=True,
    )
    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
