"""package featured cards

Revision ID: f5a6b7c8d9e0
Revises: f4a5b6c7d8e9
Create Date: 2026-05-28 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "f5a6b7c8d9e0"
down_revision: str | None = "f4a5b6c7d8e9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "packages",
        sa.Column("is_featured", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "packages",
        sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_index(
        op.f("ix_packages_is_featured"), "packages", ["is_featured"], unique=False
    )
    op.create_index(
        op.f("ix_packages_display_order"), "packages", ["display_order"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_packages_display_order"), table_name="packages")
    op.drop_index(op.f("ix_packages_is_featured"), table_name="packages")
    op.drop_column("packages", "display_order")
    op.drop_column("packages", "is_featured")
