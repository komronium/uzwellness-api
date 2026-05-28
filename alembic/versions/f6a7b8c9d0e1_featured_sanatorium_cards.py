"""featured sanatorium cards

Revision ID: f6a7b8c9d0e1
Revises: f5a6b7c8d9e0
Create Date: 2026-05-28 20:18:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "f6a7b8c9d0e1"
down_revision: str | None = "f5a6b7c8d9e0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sanatoriums",
        sa.Column("is_featured", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "sanatoriums",
        sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_index(
        op.f("ix_sanatoriums_is_featured"),
        "sanatoriums",
        ["is_featured"],
        unique=False,
    )
    op.create_index(
        op.f("ix_sanatoriums_display_order"),
        "sanatoriums",
        ["display_order"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_sanatoriums_display_order"), table_name="sanatoriums")
    op.drop_index(op.f("ix_sanatoriums_is_featured"), table_name="sanatoriums")
    op.drop_column("sanatoriums", "display_order")
    op.drop_column("sanatoriums", "is_featured")
