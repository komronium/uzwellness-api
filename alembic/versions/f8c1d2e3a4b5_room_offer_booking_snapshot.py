"""room offer booking snapshot

Revision ID: f8c1d2e3a4b5
Revises: f7b8c9d0e1f2
Create Date: 2026-06-05 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f8c1d2e3a4b5"
down_revision: str | None = "f7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("bookings", sa.Column("adults", sa.Integer()))
    op.add_column("bookings", sa.Column("children", sa.Integer()))
    op.add_column(
        "bookings",
        sa.Column(
            "room_distribution",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
    )
    op.add_column(
        "bookings",
        sa.Column(
            "treatment_selections",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
    )
    op.add_column(
        "bookings",
        sa.Column(
            "guest_options",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
    )
    op.add_column(
        "bookings",
        sa.Column(
            "offer_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("bookings", "offer_snapshot")
    op.drop_column("bookings", "guest_options")
    op.drop_column("bookings", "treatment_selections")
    op.drop_column("bookings", "room_distribution")
    op.drop_column("bookings", "children")
    op.drop_column("bookings", "adults")
