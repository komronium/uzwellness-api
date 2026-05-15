"""rename room_categories to rooms and room_category_id columns

Revision ID: a4b1c7e2d8f9
Revises: f3a9b2c7d1e8
Create Date: 2026-05-15 00:00:01.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "a4b1c7e2d8f9"
down_revision: Union[str, None] = "f3a9b2c7d1e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.rename_table("room_categories", "rooms")

    op.alter_column("bookings", "room_category_id", new_column_name="room_id")
    op.alter_column("room_availability", "room_category_id", new_column_name="room_id")
    op.alter_column("room_price_periods", "room_category_id", new_column_name="room_id")

    op.execute(
        "ALTER INDEX IF EXISTS ix_bookings_room_category_id "
        "RENAME TO ix_bookings_room_id"
    )
    op.execute(
        "ALTER INDEX IF EXISTS ix_room_availability_room_category_id "
        "RENAME TO ix_room_availability_room_id"
    )
    op.execute(
        "ALTER INDEX IF EXISTS ix_room_price_periods_room_category_id "
        "RENAME TO ix_room_price_periods_room_id"
    )


def downgrade() -> None:
    op.execute(
        "ALTER INDEX IF EXISTS ix_room_price_periods_room_id "
        "RENAME TO ix_room_price_periods_room_category_id"
    )
    op.execute(
        "ALTER INDEX IF EXISTS ix_room_availability_room_id "
        "RENAME TO ix_room_availability_room_category_id"
    )
    op.execute(
        "ALTER INDEX IF EXISTS ix_bookings_room_id "
        "RENAME TO ix_bookings_room_category_id"
    )

    op.alter_column("room_price_periods", "room_id", new_column_name="room_category_id")
    op.alter_column("room_availability", "room_id", new_column_name="room_category_id")
    op.alter_column("bookings", "room_id", new_column_name="room_category_id")

    op.rename_table("rooms", "room_categories")
