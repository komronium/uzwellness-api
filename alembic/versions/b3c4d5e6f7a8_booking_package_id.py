"""bookings.package_id + extend XOR check to include packages

Revision ID: b3c4d5e6f7a8
Revises: a95eeecef8d6
Create Date: 2026-05-20 22:30:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b3c4d5e6f7a8"
down_revision: Union[str, None] = "a95eeecef8d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "bookings",
        sa.Column("package_id", sa.Uuid(), nullable=True),
    )
    op.create_index(
        op.f("ix_bookings_package_id"),
        "bookings",
        ["package_id"],
        unique=False,
    )
    op.create_foreign_key(
        op.f("fk_bookings_package_id_packages"),
        "bookings",
        "packages",
        ["package_id"],
        ["id"],
        ondelete="SET NULL",
    )
    # Replace the room XOR program check with a one-of-three check covering
    # package bookings.
    op.drop_constraint(
        "ck_bookings_room_xor_program", "bookings", type_="check"
    )
    op.create_check_constraint(
        "ck_bookings_one_of_room_program_package",
        "bookings",
        "num_nonnulls(room_id, program_id, package_id) = 1",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_bookings_one_of_room_program_package", "bookings", type_="check"
    )
    op.create_check_constraint(
        "ck_bookings_room_xor_program",
        "bookings",
        "(room_id IS NULL) <> (program_id IS NULL)",
    )
    op.drop_constraint(
        op.f("fk_bookings_package_id_packages"), "bookings", type_="foreignkey"
    )
    op.drop_index(op.f("ix_bookings_package_id"), table_name="bookings")
    op.drop_column("bookings", "package_id")
