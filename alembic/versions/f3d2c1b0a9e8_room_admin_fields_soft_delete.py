"""room admin fields soft delete

Revision ID: f3d2c1b0a9e8
Revises: f2c4e6a8b0d1
Create Date: 2026-06-02 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f3d2c1b0a9e8"
down_revision: str | None = "f2c4e6a8b0d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "rooms",
        sa.Column("room_size_policy", sa.String(length=30), server_default="same_size"),
    )
    op.add_column(
        "rooms",
        sa.Column("smoking_policy", sa.String(length=30), server_default="non_smoking"),
    )
    op.add_column("rooms", sa.Column("window_policy", sa.String(length=40)))
    op.add_column("rooms", sa.Column("window_description", sa.String(length=255)))
    op.add_column(
        "rooms",
        sa.Column(
            "accommodation_type", sa.String(length=30), server_default="hotel_room"
        ),
    )
    op.add_column("rooms", sa.Column("gender_restriction", sa.String(length=20)))
    op.add_column("rooms", sa.Column("max_child_rate_children", sa.SmallInteger()))
    op.add_column(
        "rooms",
        sa.Column(
            "room_advisories",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
        ),
    )
    op.add_column("rooms", sa.Column("display_order", sa.Integer(), server_default="0"))
    op.add_column("rooms", sa.Column("deleted_at", sa.DateTime(timezone=True)))

    op.execute(
        """
        UPDATE rooms
        SET
            smoking_policy = CASE
                WHEN smoking_allowed THEN 'smoking_permitted'
                ELSE 'non_smoking'
            END,
            window_policy = CASE
                WHEN room_features ->> 'has_window' = 'true'
                    THEN 'all_rooms_have_windows'
                WHEN room_features ->> 'has_window' = 'false'
                    THEN 'no_rooms_have_windows'
                ELSE NULL
            END
        """
    )
    op.alter_column("rooms", "room_size_policy", nullable=False)
    op.alter_column("rooms", "smoking_policy", nullable=False)
    op.alter_column("rooms", "accommodation_type", nullable=False)
    op.alter_column("rooms", "room_advisories", nullable=False)
    op.alter_column("rooms", "display_order", nullable=False)


def downgrade() -> None:
    op.drop_column("rooms", "deleted_at")
    op.drop_column("rooms", "display_order")
    op.drop_column("rooms", "room_advisories")
    op.drop_column("rooms", "max_child_rate_children")
    op.drop_column("rooms", "gender_restriction")
    op.drop_column("rooms", "accommodation_type")
    op.drop_column("rooms", "window_description")
    op.drop_column("rooms", "window_policy")
    op.drop_column("rooms", "smoking_policy")
    op.drop_column("rooms", "room_size_policy")
