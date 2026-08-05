from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Index, String, Uuid
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.ids import uuid7
from app.models.base import TimestampMixin


class UzumCheckoutCallbackKind(StrEnum):
    ACQUIRING = "acquiring"  # financial operation result
    EVENT = "event"  # business event, e.g. the customer closed the form
    RECEIPT = "receipt"  # fiscal receipt generated


class UzumCheckoutEvent(TimestampMixin, Base):
    """Append-only log of callbacks Uzum Checkout sent us.

    Checkout signs nothing, so a callback body is untrusted input: it is
    recorded here and acknowledged, never acted on directly. Applying it to a
    payment happens separately, after ``getOrderStatus`` confirms the state
    with Uzum — until then ``processed_at`` stays NULL.

    Keeping every delivery (including Uzum's up-to-5 retries) is deliberate:
    during onboarding this table is the only record of what they actually
    send, including the source IP we need for the nginx allowlist.
    """

    __tablename__ = "uzum_checkout_events"
    __table_args__ = (
        Index("ix_uzum_checkout_events_unprocessed", "processed_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    kind: Mapped[UzumCheckoutCallbackKind] = mapped_column(
        SQLEnum(
            UzumCheckoutCallbackKind,
            native_enum=False,
            length=20,
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
        index=True,
    )

    # Checkout's own order id, and the number we sent as `orderNumber`.
    order_id: Mapped[str | None] = mapped_column(String(64), index=True)
    order_number: Mapped[str | None] = mapped_column(String(36), index=True)

    operation_type: Mapped[str | None] = mapped_column(String(32))
    operation_state: Mapped[str | None] = mapped_column(String(16))
    event_type: Mapped[str | None] = mapped_column(String(32))
    receipt_type: Mapped[str | None] = mapped_column(String(16))
    receipt_url: Mapped[str | None] = mapped_column(String(2083))
    rrn: Mapped[str | None] = mapped_column(String(64))

    source_ip: Mapped[str | None] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )

    # NULL until the callback has been verified against Uzum and applied.
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
