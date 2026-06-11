"""Store exchange rates with 2 decimal places (display precision is enough)

Revision ID: c4f8a2d6e9b1
Revises: b7d2e9f4a1c8
Create Date: 2026-06-11

"""

import sqlalchemy as sa
from alembic import op

revision = "c4f8a2d6e9b1"
down_revision = "b7d2e9f4a1c8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Postgres rounds existing values on the type change.
    op.alter_column(
        "exchange_rates",
        "rate",
        existing_type=sa.Numeric(18, 6),
        type_=sa.Numeric(18, 2),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "exchange_rates",
        "rate",
        existing_type=sa.Numeric(18, 2),
        type_=sa.Numeric(18, 6),
        existing_nullable=False,
    )
