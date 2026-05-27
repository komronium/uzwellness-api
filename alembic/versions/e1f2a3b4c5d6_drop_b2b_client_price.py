"""drop b2b client price

Revision ID: e1f2a3b4c5d6
Revises: d8e9f0a1b2c3
Create Date: 2026-05-27 23:55:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "e1f2a3b4c5d6"
down_revision: str | None = "d8e9f0a1b2c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("bookings", "b2b_client_price")


def downgrade() -> None:
    op.add_column(
        "bookings",
        sa.Column("b2b_client_price", sa.Numeric(12, 2), nullable=True),
    )
