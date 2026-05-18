"""lazy room availability: move units_total to Room.inventory_count

Revision ID: a5b3c8d9e2f1
Revises: f9c2a3b8d4e7
Create Date: 2026-05-18 00:00:00
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "a5b3c8d9e2f1"
down_revision: Union[str, None] = "f9c2a3b8d4e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add new columns
    op.add_column(
        "rooms",
        sa.Column(
            "inventory_count", sa.Integer(), nullable=False, server_default="1"
        ),
    )
    op.add_column(
        "room_availability",
        sa.Column(
            "units_blocked", sa.Integer(), nullable=False, server_default="0"
        ),
    )
    op.add_column(
        "room_availability",
        sa.Column(
            "units_booked", sa.Integer(), nullable=False, server_default="0"
        ),
    )

    # 2. Compute inventory_count from existing data
    op.execute(
        """
        UPDATE rooms r
        SET inventory_count = COALESCE(
            (SELECT MAX(units_total) FROM room_availability WHERE room_id = r.id),
            1
        )
        """
    )

    # 3. Compute units_booked
    op.execute(
        """
        UPDATE room_availability
        SET units_booked = GREATEST(units_total - units_available, 0)
        """
    )

    # 4. Compute units_blocked (inventory_count - units_total, when room
    #    has been partially closed on this date)
    op.execute(
        """
        UPDATE room_availability ra
        SET units_blocked = GREATEST(
            (SELECT inventory_count FROM rooms WHERE id = ra.room_id) - ra.units_total,
            0
        )
        """
    )

    # 5. Drop no-op rows (lazy materialization: only exception rows remain)
    op.execute(
        """
        DELETE FROM room_availability
        WHERE units_blocked = 0 AND units_booked = 0
        """
    )

    # 6. Drop old columns
    op.drop_column("room_availability", "units_total")
    op.drop_column("room_availability", "units_available")

    # 7. CHECK constraint
    op.create_check_constraint(
        "ck_room_availability_nonneg",
        "room_availability",
        "units_blocked >= 0 AND units_booked >= 0",
    )

    # 8. Drop server defaults (application-managed from now on)
    op.alter_column("rooms", "inventory_count", server_default=None)
    op.alter_column("room_availability", "units_blocked", server_default=None)
    op.alter_column("room_availability", "units_booked", server_default=None)


def downgrade() -> None:
    op.drop_constraint("ck_room_availability_nonneg", "room_availability")

    op.add_column(
        "room_availability",
        sa.Column("units_total", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "room_availability",
        sa.Column(
            "units_available", sa.Integer(), nullable=False, server_default="1"
        ),
    )

    # Best-effort restore (lossy: implicit dates aren't rematerialized)
    op.execute(
        """
        UPDATE room_availability ra
        SET units_total = (SELECT inventory_count FROM rooms WHERE id = ra.room_id)
                          - ra.units_blocked,
            units_available = (SELECT inventory_count FROM rooms WHERE id = ra.room_id)
                          - ra.units_blocked - ra.units_booked
        """
    )

    op.alter_column("room_availability", "units_total", server_default=None)
    op.alter_column("room_availability", "units_available", server_default=None)

    op.drop_column("room_availability", "units_booked")
    op.drop_column("room_availability", "units_blocked")
    op.drop_column("rooms", "inventory_count")
