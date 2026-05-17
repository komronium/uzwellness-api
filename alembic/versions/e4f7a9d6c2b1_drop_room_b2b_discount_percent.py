"""drop rooms.b2b_discount_percent

Revision ID: e4f7a9d6c2b1
Revises: b8d7e2f4a1c3
Create Date: 2026-05-17 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e4f7a9d6c2b1"
down_revision: Union[str, None] = "b8d7e2f4a1c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("rooms", "b2b_discount_percent")


def downgrade() -> None:
    op.add_column(
        "rooms",
        sa.Column("b2b_discount_percent", sa.Numeric(5, 2), nullable=True),
    )
