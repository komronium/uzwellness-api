"""room_availability unique constraint and index cleanup

Revision ID: a1c4e7f9b2d5
Revises: 997dc5e40eca
Create Date: 2026-06-10 23:05:00.000000

The model has always declared UNIQUE(room_id, date) on room_availability but
the constraint never made it into the database; the booking paths rely on it
(reserve_units assumes one row per room per day). Duplicates, if any, are
merged keeping the row with the most units in use, so availability never
appears larger than the strictest row claimed.

treatment_focuses carried a redundant index on its primary key and both a
unique constraint and a separate non-unique index on slug; collapse to a
single unique index matching the model.
"""

from collections.abc import Sequence

from alembic import op


revision: str = "a1c4e7f9b2d5"
down_revision: str | None = "997dc5e40eca"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM room_availability a
        USING room_availability b
        WHERE a.room_id = b.room_id
          AND a.date = b.date
          AND (a.units_blocked + a.units_booked, a.id)
            < (b.units_blocked + b.units_booked, b.id)
        """
    )
    op.create_unique_constraint(
        "uq_room_availability_date", "room_availability", ["room_id", "date"]
    )

    op.drop_index("ix_treatment_focuses_id", table_name="treatment_focuses")
    op.drop_index("ix_treatment_focuses_slug", table_name="treatment_focuses")
    op.drop_constraint("treatment_focuses_slug_key", "treatment_focuses", type_="unique")
    op.create_index(
        "ix_treatment_focuses_slug", "treatment_focuses", ["slug"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_treatment_focuses_slug", table_name="treatment_focuses")
    op.create_unique_constraint(
        "treatment_focuses_slug_key", "treatment_focuses", ["slug"]
    )
    op.create_index(
        "ix_treatment_focuses_slug", "treatment_focuses", ["slug"], unique=False
    )
    op.create_index("ix_treatment_focuses_id", "treatment_focuses", ["id"], unique=False)

    op.drop_constraint(
        "uq_room_availability_date", "room_availability", type_="unique"
    )
