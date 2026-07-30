import uuid
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import Boolean, CheckConstraint, Index, Numeric, String, Uuid, text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin
from app.core.ids import uuid7


class UserRole(StrEnum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    AGENT = "agent"
    TRANSFER_ADMIN = "transfer_admin"
    CUSTOMER = "customer"


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        # Product decision: exactly one transfer operator platform-wide. Relax
        # this index (and move the commission to AppConfig) if a backup
        # operator is ever needed — the API keys off the role, not the count.
        Index(
            "uq_users_single_transfer_admin",
            "role",
            unique=True,
            postgresql_where=text("role = 'transfer_admin'"),
        ),
        CheckConstraint(
            "transfer_commission_percent IS NULL "
            "OR transfer_commission_percent BETWEEN 0 AND 100",
            name="ck_users_transfer_commission_percent_range",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SQLEnum(
            UserRole,
            native_enum=False,
            length=20,
            values_callable=lambda enum: [e.value for e in enum],
        ),
        default=UserRole.CUSTOMER,
        nullable=False,
    )
    full_name: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Platform cut on the transfer portion of an order. Only meaningful for
    # transfer_admin; snapshotted onto each TransferRequest at pricing time.
    transfer_commission_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
