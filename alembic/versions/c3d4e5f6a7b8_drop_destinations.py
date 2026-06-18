"""drop destinations (merged into regions)

Revision ID: c3d4e5f6a7b8
Revises: c4f8a2d6e9b1
Create Date: 2026-06-18 00:00:00.000000

Destinations were a separate "homepage tile" catalog that overlapped with
the `regions` viloyat catalog (e.g. "Tashkent Region", "Samarkand",
"Fergana Valley"), so the FE rendered both lists and regions appeared
doubled. The concept is removed entirely; `regions` is now the single
geographic grouping. This drops the `sanatoriums.destination_id` FK and the
`destinations` table.

downgrade() recreates the table + column structure (post-simplify shape:
`hero_image_url`, no `country`) but does not re-seed any rows.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "c4f8a2d6e9b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index(op.f("ix_sanatoriums_destination_id"), table_name="sanatoriums")
    op.drop_constraint(
        op.f("fk_sanatoriums_destination_id_destinations"),
        "sanatoriums",
        type_="foreignkey",
    )
    op.drop_column("sanatoriums", "destination_id")

    op.drop_index(op.f("ix_destinations_is_active"), table_name="destinations")
    op.drop_index(op.f("ix_destinations_slug"), table_name="destinations")
    op.drop_table("destinations")


def downgrade() -> None:
    op.create_table(
        "destinations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column(
            "name",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "tagline",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "description",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("hero_image_url", sa.String(length=500), nullable=True),
        sa.Column("lat", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("lng", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
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
    )
    op.create_index(op.f("ix_destinations_slug"), "destinations", ["slug"], unique=True)
    op.create_index(op.f("ix_destinations_is_active"), "destinations", ["is_active"])

    op.add_column(
        "sanatoriums",
        sa.Column("destination_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_sanatoriums_destination_id_destinations"),
        "sanatoriums",
        "destinations",
        ["destination_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_sanatoriums_destination_id"),
        "sanatoriums",
        ["destination_id"],
    )
