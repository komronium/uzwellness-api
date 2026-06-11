"""Add source column to exchange_rates (manual vs cbu sync)

Revision ID: b7d2e9f4a1c8
Revises: a1c4e7f9b2d5
Create Date: 2026-06-11

"""

import sqlalchemy as sa
from alembic import op

revision = "b7d2e9f4a1c8"
down_revision = "a1c4e7f9b2d5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "exchange_rates",
        sa.Column(
            "source", sa.String(length=10), nullable=False, server_default="manual"
        ),
    )


def downgrade() -> None:
    op.drop_column("exchange_rates", "source")
