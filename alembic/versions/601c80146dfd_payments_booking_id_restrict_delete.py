"""payments booking_id restrict delete

Revision ID: 601c80146dfd
Revises: 9136b80e268a
Create Date: 2026-09-04 00:00:00.000000

Every other financial/history FK in this schema (bookings -> user/room/program,
transfer_requests -> bookings) uses SET NULL so deleting a parent never
destroys the record; payments.booking_id was still the original CASCADE,
so deleting a booking would silently erase its payment history instead of
being blocked. Nothing deletes bookings today, so this closes a landmine
rather than fixing a live bug: RESTRICT rather than SET NULL, since a
payment with no booking would be meaningless for reconciliation.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "601c80146dfd"
down_revision: str | None = "9136b80e268a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("payments_booking_id_fkey", "payments", type_="foreignkey")
    op.create_foreign_key(
        "payments_booking_id_fkey",
        "payments",
        "bookings",
        ["booking_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint("payments_booking_id_fkey", "payments", type_="foreignkey")
    op.create_foreign_key(
        "payments_booking_id_fkey",
        "payments",
        "bookings",
        ["booking_id"],
        ["id"],
        ondelete="CASCADE",
    )
