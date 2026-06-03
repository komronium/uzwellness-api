"""amenity catalog scopes and selection details

Revision ID: f4e5d6c7b8a9
Revises: f3d2c1b0a9e8
Create Date: 2026-06-02 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f4e5d6c7b8a9"
down_revision: str | None = "f3d2c1b0a9e8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("amenities", sa.Column("code", sa.String(length=80), nullable=True))
    op.add_column(
        "amenities",
        sa.Column("scope", sa.String(length=20), server_default="both", nullable=False),
    )
    op.add_column(
        "amenities",
        sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "amenities",
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
    )
    op.create_index("ix_amenities_code", "amenities", ["code"], unique=True)
    op.create_index("ix_amenities_scope", "amenities", ["scope"], unique=False)

    op.add_column(
        "sanatorium_amenities",
        sa.Column("status", sa.String(length=20), server_default="yes", nullable=False),
    )
    op.add_column(
        "sanatorium_amenities",
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
    )
    op.add_column(
        "sanatorium_amenities",
        sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
    )
    op.execute(
        """
        UPDATE sanatorium_amenities
        SET status = CASE WHEN is_available THEN 'yes' ELSE 'no' END
        """
    )

    op.add_column(
        "room_amenities",
        sa.Column("status", sa.String(length=20), server_default="yes", nullable=False),
    )
    op.add_column(
        "room_amenities",
        sa.Column("cost", sa.String(length=20), server_default="free", nullable=False),
    )
    op.add_column(
        "room_amenities",
        sa.Column("is_available", sa.Boolean(), server_default="true", nullable=False),
    )
    op.add_column(
        "room_amenities",
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
    )
    op.add_column(
        "room_amenities",
        sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("room_amenities", "display_order")
    op.drop_column("room_amenities", "details")
    op.drop_column("room_amenities", "is_available")
    op.drop_column("room_amenities", "cost")
    op.drop_column("room_amenities", "status")

    op.drop_column("sanatorium_amenities", "display_order")
    op.drop_column("sanatorium_amenities", "details")
    op.drop_column("sanatorium_amenities", "status")

    op.drop_index("ix_amenities_scope", table_name="amenities")
    op.drop_index("ix_amenities_code", table_name="amenities")
    op.drop_column("amenities", "is_active")
    op.drop_column("amenities", "display_order")
    op.drop_column("amenities", "scope")
    op.drop_column("amenities", "code")
