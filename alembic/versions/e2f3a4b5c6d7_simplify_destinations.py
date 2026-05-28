"""simplify destinations

Revision ID: e2f3a4b5c6d7
Revises: e1f2a3b4c5d6
Create Date: 2026-05-28 10:20:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "e2f3a4b5c6d7"
down_revision: str | None = "e1f2a3b4c5d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("destinations", "hero_image", new_column_name="hero_image_url")
    op.drop_column("destinations", "country")


def downgrade() -> None:
    op.add_column(
        "destinations",
        sa.Column(
            "country",
            sa.String(length=80),
            nullable=False,
            server_default="Uzbekistan",
        ),
    )
    op.alter_column("destinations", "hero_image_url", new_column_name="hero_image")
