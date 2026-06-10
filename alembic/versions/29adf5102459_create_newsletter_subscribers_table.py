"""create newsletter subscribers table

Revision ID: 29adf5102459
Revises: f9f0a1b2c3d4
Create Date: 2026-06-10 16:42:51.601641

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "29adf5102459"
down_revision: str | None = "f9f0a1b2c3d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "newsletter_subscribers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_newsletter_subscribers_email"),
        "newsletter_subscribers",
        ["email"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_newsletter_subscribers_email"), table_name="newsletter_subscribers"
    )
    op.drop_table("newsletter_subscribers")
