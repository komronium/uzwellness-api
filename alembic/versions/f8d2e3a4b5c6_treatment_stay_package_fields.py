"""treatment stay package fields

Revision ID: f8d2e3a4b5c6
Revises: f8c1d2e3a4b5
Create Date: 2026-06-05 00:00:01.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f8d2e3a4b5c6"
down_revision: str | None = "f8c1d2e3a4b5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "treatment_programs",
        sa.Column(
            "program_type",
            sa.String(length=30),
            server_default="session",
            nullable=False,
        ),
    )
    op.add_column(
        "treatment_programs",
        sa.Column(
            "stay_package_kind",
            sa.String(length=20),
            server_default="treatment",
            nullable=False,
        ),
    )
    op.add_column(
        "treatment_programs",
        sa.Column(
            "guest_applicability",
            sa.String(length=20),
            server_default="all",
            nullable=False,
        ),
    )
    op.add_column(
        "treatment_programs",
        sa.Column(
            "medical_exam_count", sa.Integer(), server_default="0", nullable=False
        ),
    )
    op.add_column(
        "treatment_programs",
        sa.Column(
            "medical_procedure_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "treatment_programs",
        sa.Column(
            "drink_cure_included",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
    )
    op.add_column("treatment_programs", sa.Column("sauna_entries", sa.Integer()))
    op.add_column(
        "treatment_programs",
        sa.Column(
            "pool_access_included",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
    )
    op.add_column(
        "treatment_programs",
        sa.Column(
            "included_services",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
    )
    op.add_column(
        "treatment_programs",
        sa.Column(
            "is_default_stay_package",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
    )
    op.add_column(
        "treatment_programs",
        sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_index(
        "ix_treatment_programs_program_type",
        "treatment_programs",
        ["program_type"],
    )
    op.create_index(
        "ix_treatment_programs_stay_package_kind",
        "treatment_programs",
        ["stay_package_kind"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_treatment_programs_stay_package_kind",
        table_name="treatment_programs",
    )
    op.drop_index("ix_treatment_programs_program_type", table_name="treatment_programs")
    op.drop_column("treatment_programs", "display_order")
    op.drop_column("treatment_programs", "is_default_stay_package")
    op.drop_column("treatment_programs", "included_services")
    op.drop_column("treatment_programs", "pool_access_included")
    op.drop_column("treatment_programs", "sauna_entries")
    op.drop_column("treatment_programs", "drink_cure_included")
    op.drop_column("treatment_programs", "medical_procedure_count")
    op.drop_column("treatment_programs", "medical_exam_count")
    op.drop_column("treatment_programs", "guest_applicability")
    op.drop_column("treatment_programs", "stay_package_kind")
    op.drop_column("treatment_programs", "program_type")
