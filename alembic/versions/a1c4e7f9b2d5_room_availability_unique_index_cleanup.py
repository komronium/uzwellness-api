"""room_availability unique constraint and index cleanup

Revision ID: a1c4e7f9b2d5
Revises: 997dc5e40eca
Create Date: 2026-06-10 23:05:00.000000

The model declares UNIQUE(room_id, date) on room_availability but some
environments never got the constraint; the booking paths rely on it
(reserve_units assumes one row per room per day). Duplicates, if any, are
merged keeping the row with the most units in use, so availability never
appears larger than the strictest row claimed.

treatment_focuses carried a redundant index on its primary key and both a
unique constraint and a separate non-unique index on slug; collapse to a
single unique index matching the model.

Every step is conditional: environments drifted (the constraint and index
set differs between databases), so the migration converges any starting
state to the model.
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
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'uq_room_availability_date'
            ) AND NOT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE indexname = 'uq_room_availability_date'
            ) THEN
                ALTER TABLE room_availability
                    ADD CONSTRAINT uq_room_availability_date
                    UNIQUE (room_id, date);
            END IF;
        END $$;
        """
    )

    op.execute("DROP INDEX IF EXISTS ix_treatment_focuses_id")
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE indexname = 'ix_treatment_focuses_slug'
                  AND indexdef LIKE 'CREATE UNIQUE INDEX%'
            ) THEN
                DROP INDEX IF EXISTS ix_treatment_focuses_slug;
            END IF;
        END $$;
        """
    )
    op.execute(
        "ALTER TABLE treatment_focuses"
        " DROP CONSTRAINT IF EXISTS treatment_focuses_slug_key"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_treatment_focuses_slug"
        " ON treatment_focuses (slug)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_treatment_focuses_slug")
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'treatment_focuses_slug_key'
            ) THEN
                ALTER TABLE treatment_focuses
                    ADD CONSTRAINT treatment_focuses_slug_key UNIQUE (slug);
            END IF;
        END $$;
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_treatment_focuses_slug"
        " ON treatment_focuses (slug)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_treatment_focuses_id"
        " ON treatment_focuses (id)"
    )
    op.execute(
        "ALTER TABLE room_availability"
        " DROP CONSTRAINT IF EXISTS uq_room_availability_date"
    )
