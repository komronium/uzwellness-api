"""Package redesign: sanatorium_id + room_id required, drop HOTEL, 3-branch check

Revision ID: c5d8e2f1a3b7
Revises: 844708bf396d
Create Date: 2026-05-21 12:00:00.000000

Packages now anchor to exactly one sanatorium AND one room category. The
admin picks both at package creation. The customer just picks a package —
they never choose a room. This makes the package a real product with a
single price, single inventory line, and unambiguous availability draws.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c5d8e2f1a3b7"
down_revision: Union[str, None] = "844708bf396d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop legacy HOTEL line items — sanatorium accommodation is now implicit.
    op.execute("DELETE FROM package_items WHERE item_type = 'hotel'")

    # ── sanatorium_id: nullable → NOT NULL, FK SET NULL → RESTRICT ─────────
    op.execute("DELETE FROM packages WHERE sanatorium_id IS NULL")
    op.alter_column(
        "packages", "sanatorium_id", existing_type=sa.Uuid(), nullable=False
    )
    op.drop_constraint(
        "packages_sanatorium_id_fkey", "packages", type_="foreignkey"
    )
    op.create_foreign_key(
        "packages_sanatorium_id_fkey",
        "packages",
        "sanatoriums",
        ["sanatorium_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # ── room_id: new column, backfilled from same sanatorium, NOT NULL ────
    op.add_column(
        "packages", sa.Column("room_id", sa.Uuid(), nullable=True)
    )
    # Backfill: pick the cheapest active room in the same sanatorium whose
    # currency matches the package. Existing packages without a viable room
    # are deleted (the data is demo-only and can be re-seeded).
    op.execute(
        """
        UPDATE packages p
        SET room_id = (
            SELECT r.id FROM rooms r
            WHERE r.sanatorium_id = p.sanatorium_id
              AND r.base_currency = p.currency
              AND r.is_active = TRUE
            ORDER BY r.base_price
            LIMIT 1
        )
        """
    )
    op.execute("DELETE FROM packages WHERE room_id IS NULL")
    op.alter_column(
        "packages", "room_id", existing_type=sa.Uuid(), nullable=False
    )
    op.create_foreign_key(
        "packages_room_id_fkey",
        "packages",
        "rooms",
        ["room_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        op.f("ix_packages_room_id"), "packages", ["room_id"], unique=False
    )

    # ── booking link constraint: package bookings carry both package + room.
    op.drop_constraint(
        "ck_bookings_one_of_room_program_package", "bookings", type_="check"
    )
    op.create_check_constraint(
        "ck_bookings_type_links_consistent",
        "bookings",
        """
        (booking_type = 'room'    AND room_id IS NOT NULL AND program_id IS NULL    AND package_id IS NULL)
        OR
        (booking_type = 'session' AND program_id IS NOT NULL AND room_id IS NULL    AND package_id IS NULL)
        OR
        (booking_type = 'package' AND package_id IS NOT NULL AND room_id IS NOT NULL AND program_id IS NULL)
        """,
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_bookings_type_links_consistent", "bookings", type_="check"
    )
    op.create_check_constraint(
        "ck_bookings_one_of_room_program_package",
        "bookings",
        "num_nonnulls(room_id, program_id, package_id) = 1",
    )

    op.drop_index(op.f("ix_packages_room_id"), table_name="packages")
    op.drop_constraint("packages_room_id_fkey", "packages", type_="foreignkey")
    op.drop_column("packages", "room_id")

    op.drop_constraint(
        "packages_sanatorium_id_fkey", "packages", type_="foreignkey"
    )
    op.create_foreign_key(
        "packages_sanatorium_id_fkey",
        "packages",
        "sanatoriums",
        ["sanatorium_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.alter_column(
        "packages", "sanatorium_id", existing_type=sa.Uuid(), nullable=True
    )
