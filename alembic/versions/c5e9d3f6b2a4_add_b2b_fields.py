"""add b2b discount + booking guest_details + is_b2b

Revision ID: c5e9d3f6b2a4
Revises: a4b1c7e2d8f9
Create Date: 2026-05-15 00:00:02.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c5e9d3f6b2a4"
down_revision: Union[str, None] = "a4b1c7e2d8f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "rooms",
        sa.Column("b2b_discount_percent", sa.Numeric(5, 2), nullable=True),
    )
    op.add_column(
        "bookings",
        sa.Column(
            "is_b2b",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "bookings",
        sa.Column(
            "guest_details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
    )
    op.add_column(
        "bookings",
        sa.Column("b2b_client_price", sa.Numeric(12, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("bookings", "b2b_client_price")
    op.drop_column("bookings", "guest_details")
    op.drop_column("bookings", "is_b2b")
    op.drop_column("rooms", "b2b_discount_percent")
