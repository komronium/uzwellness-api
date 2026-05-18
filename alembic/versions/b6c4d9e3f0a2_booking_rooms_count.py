"""booking rooms_count for multi-unit bookings

Revision ID: b6c4d9e3f0a2
Revises: a5b3c8d9e2f1
Create Date: 2026-05-18 00:30:00
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "b6c4d9e3f0a2"
down_revision: Union[str, None] = "a5b3c8d9e2f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "bookings",
        sa.Column(
            "rooms_count", sa.Integer(), nullable=False, server_default="1"
        ),
    )
    op.create_check_constraint(
        "ck_bookings_rooms_count_positive",
        "bookings",
        "rooms_count >= 1",
    )


def downgrade() -> None:
    op.drop_constraint("ck_bookings_rooms_count_positive", "bookings")
    op.drop_column("bookings", "rooms_count")
