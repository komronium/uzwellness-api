from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.ids import uuid7


class VisaStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    ISSUED = "issued"
    REJECTED = "rejected"


class VisaPurpose(StrEnum):
    TOURISM = "tourism"
    TREATMENT = "treatment"
    BUSINESS = "business"
    OTHER = "other"


class VisaRequest(Base):
    """Customer-submitted visa assistance request, processed by super_admin."""

    __tablename__ = "visa_requests"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    booking_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("bookings.id", ondelete="SET NULL"), index=True
    )

    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    citizenship: Mapped[str] = mapped_column(String(120), nullable=False)
    passport_number: Mapped[str] = mapped_column(String(64), nullable=False)
    date_of_birth: Mapped[date] = mapped_column(Date, nullable=False)
    arrival_date: Mapped[date] = mapped_column(Date, nullable=False)
    departure_date: Mapped[date] = mapped_column(Date, nullable=False)
    purpose: Mapped[VisaPurpose] = mapped_column(
        SQLEnum(
            VisaPurpose,
            native_enum=False,
            length=20,
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
        default=VisaPurpose.TOURISM,
    )

    passport_scan_url: Mapped[str | None] = mapped_column(String(500))
    issued_document_url: Mapped[str | None] = mapped_column(String(500))

    status: Mapped[VisaStatus] = mapped_column(
        SQLEnum(
            VisaStatus,
            native_enum=False,
            length=20,
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
        default=VisaStatus.PENDING,
        index=True,
    )
    admin_notes: Mapped[str | None] = mapped_column(Text)

    contact_email: Mapped[str | None] = mapped_column(String(255))
    contact_phone: Mapped[str | None] = mapped_column(String(32))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
