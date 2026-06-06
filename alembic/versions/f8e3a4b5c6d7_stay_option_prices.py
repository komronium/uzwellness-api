"""stay option prices

Revision ID: f8e3a4b5c6d7
Revises: f8d2e3a4b5c6
Create Date: 2026-06-06 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f8e3a4b5c6d7"
down_revision: str | None = "f8d2e3a4b5c6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sanatorium_stay_option_prices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("sanatorium_id", sa.Uuid(), nullable=False),
        sa.Column("guest_type", sa.String(length=20), nullable=False),
        sa.Column("board", sa.String(length=20), nullable=False),
        sa.Column("treatment_included", sa.Boolean(), nullable=False),
        sa.Column(
            "price_delta",
            sa.Numeric(precision=12, scale=2),
            server_default="0",
            nullable=False,
        ),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("is_available", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["sanatorium_id"], ["sanatoriums.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "sanatorium_id",
            "guest_type",
            "board",
            "treatment_included",
            name="uq_sanatorium_stay_option_price",
        ),
    )
    op.create_index(
        op.f("ix_sanatorium_stay_option_prices_sanatorium_id"),
        "sanatorium_stay_option_prices",
        ["sanatorium_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_sanatorium_stay_option_prices_sanatorium_id"),
        table_name="sanatorium_stay_option_prices",
    )
    op.drop_table("sanatorium_stay_option_prices")
