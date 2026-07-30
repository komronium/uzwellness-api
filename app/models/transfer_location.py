from __future__ import annotations

import uuid
from enum import StrEnum

from sqlalchemy import Boolean, Uuid
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.ids import uuid7
from app.models.base import TimestampMixin


class TransferLocationKind(StrEnum):
    AIRPORT = "airport"
    CITY = "city"
    SANATORIUM = "sanatorium"
    CUSTOM = "custom"


class TransferLocation(TimestampMixin, Base):
    """Structured endpoint of a transfer route.

    Tariffs are keyed by (route_from, route_to, vehicle_type), so the free-text
    ``pickup_location``/``dropoff_location`` on TransferRequest could not carry
    pricing. Those columns stay as denormalized snapshots of the names picked
    here at the moment the transfer was created.
    """

    __tablename__ = "transfer_locations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    name: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    kind: Mapped[TransferLocationKind] = mapped_column(
        SQLEnum(
            TransferLocationKind,
            native_enum=False,
            length=20,
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true", index=True
    )
