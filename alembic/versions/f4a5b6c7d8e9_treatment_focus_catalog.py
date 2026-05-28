"""treatment focus catalog

Revision ID: f4a5b6c7d8e9
Revises: e2f3a4b5c6d7
Create Date: 2026-05-28 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "f4a5b6c7d8e9"
down_revision: str | None = "e2f3a4b5c6d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "treatment_focuses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("name", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "description",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("image_url", sa.String(length=500), nullable=True),
        sa.Column("icon", sa.String(length=80), nullable=True),
        sa.Column("display_order", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index(
        op.f("ix_treatment_focuses_display_order"),
        "treatment_focuses",
        ["display_order"],
        unique=False,
    )
    op.create_index(
        op.f("ix_treatment_focuses_id"), "treatment_focuses", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_treatment_focuses_is_active"),
        "treatment_focuses",
        ["is_active"],
        unique=False,
    )
    op.create_index(
        op.f("ix_treatment_focuses_slug"), "treatment_focuses", ["slug"], unique=False
    )
    op.add_column(
        "treatment_programs", sa.Column("focus_id", sa.Uuid(), nullable=True)
    )
    op.create_index(
        op.f("ix_treatment_programs_focus_id"),
        "treatment_programs",
        ["focus_id"],
        unique=False,
    )
    op.create_foreign_key(
        op.f("fk_treatment_programs_focus_id_treatment_focuses"),
        "treatment_programs",
        "treatment_focuses",
        ["focus_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_treatment_programs_focus_id_treatment_focuses"),
        "treatment_programs",
        type_="foreignkey",
    )
    op.drop_index(op.f("ix_treatment_programs_focus_id"), table_name="treatment_programs")
    op.drop_column("treatment_programs", "focus_id")
    op.drop_index(op.f("ix_treatment_focuses_slug"), table_name="treatment_focuses")
    op.drop_index(op.f("ix_treatment_focuses_is_active"), table_name="treatment_focuses")
    op.drop_index(op.f("ix_treatment_focuses_id"), table_name="treatment_focuses")
    op.drop_index(
        op.f("ix_treatment_focuses_display_order"), table_name="treatment_focuses"
    )
    op.drop_table("treatment_focuses")
