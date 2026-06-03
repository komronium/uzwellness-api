"""review admin workflow

Revision ID: f7b8c9d0e1f2
Revises: f4e5d6c7b8a9
Create Date: 2026-06-03 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f7b8c9d0e1f2"
down_revision: str | None = "f4e5d6c7b8a9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sanatorium_reviews",
        sa.Column("booking_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "sanatorium_reviews",
        sa.Column("room_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "sanatorium_reviews",
        sa.Column(
            "source",
            sa.String(length=30),
            server_default="uzwellness",
            nullable=False,
        ),
    )
    op.add_column("sanatorium_reviews", sa.Column("external_id", sa.String(length=120)))
    op.add_column(
        "sanatorium_reviews", sa.Column("external_url", sa.String(length=500))
    )
    op.add_column(
        "sanatorium_reviews",
        sa.Column("reviewer_avatar_url", sa.String(length=500)),
    )
    op.add_column("sanatorium_reviews", sa.Column("language", sa.String(length=10)))
    op.add_column("sanatorium_reviews", sa.Column("stayed_at", sa.Date()))
    op.add_column(
        "sanatorium_reviews", sa.Column("stayed_room_name", sa.String(length=160))
    )
    op.add_column("sanatorium_reviews", sa.Column("score_label", sa.String(length=40)))
    op.add_column("sanatorium_reviews", sa.Column("translated_body", sa.Text()))
    op.add_column(
        "sanatorium_reviews",
        sa.Column(
            "positive_tags",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
    )
    op.add_column(
        "sanatorium_reviews",
        sa.Column(
            "negative_tags",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
    )
    op.add_column(
        "sanatorium_reviews",
        sa.Column(
            "photos",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
    )
    op.add_column("sanatorium_reviews", sa.Column("reply_body", sa.Text()))
    op.add_column(
        "sanatorium_reviews", sa.Column("reply_language", sa.String(length=10))
    )
    op.add_column(
        "sanatorium_reviews",
        sa.Column(
            "reply_status",
            sa.String(length=30),
            server_default="awaiting_reply",
            nullable=False,
        ),
    )
    op.add_column(
        "sanatorium_reviews",
        sa.Column("replied_at", sa.DateTime(timezone=True)),
    )
    op.add_column(
        "sanatorium_reviews",
        sa.Column("replied_by_user_id", sa.Uuid()),
    )
    op.add_column(
        "sanatorium_reviews",
        sa.Column(
            "appeal_status",
            sa.String(length=30),
            server_default="none",
            nullable=False,
        ),
    )
    op.add_column("sanatorium_reviews", sa.Column("appeal_reason", sa.Text()))
    op.add_column(
        "sanatorium_reviews",
        sa.Column("appealed_at", sa.DateTime(timezone=True)),
    )

    op.create_index(
        "ix_sanatorium_reviews_booking_id",
        "sanatorium_reviews",
        ["booking_id"],
    )
    op.create_index(
        "ix_sanatorium_reviews_room_id",
        "sanatorium_reviews",
        ["room_id"],
    )
    op.create_index(
        "ix_sanatorium_reviews_source",
        "sanatorium_reviews",
        ["source"],
    )
    op.create_index(
        "ix_sanatorium_reviews_external_id",
        "sanatorium_reviews",
        ["external_id"],
    )
    op.create_index(
        "ix_sanatorium_reviews_reply_status",
        "sanatorium_reviews",
        ["reply_status"],
    )
    op.create_foreign_key(
        "fk_sanatorium_reviews_booking_id_bookings",
        "sanatorium_reviews",
        "bookings",
        ["booking_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_sanatorium_reviews_room_id_rooms",
        "sanatorium_reviews",
        "rooms",
        ["room_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_sanatorium_reviews_replied_by_user_id_users",
        "sanatorium_reviews",
        "users",
        ["replied_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_sanatorium_reviews_replied_by_user_id_users",
        "sanatorium_reviews",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_sanatorium_reviews_room_id_rooms",
        "sanatorium_reviews",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_sanatorium_reviews_booking_id_bookings",
        "sanatorium_reviews",
        type_="foreignkey",
    )
    op.drop_index("ix_sanatorium_reviews_reply_status", table_name="sanatorium_reviews")
    op.drop_index("ix_sanatorium_reviews_external_id", table_name="sanatorium_reviews")
    op.drop_index("ix_sanatorium_reviews_source", table_name="sanatorium_reviews")
    op.drop_index("ix_sanatorium_reviews_room_id", table_name="sanatorium_reviews")
    op.drop_index("ix_sanatorium_reviews_booking_id", table_name="sanatorium_reviews")

    op.drop_column("sanatorium_reviews", "appealed_at")
    op.drop_column("sanatorium_reviews", "appeal_reason")
    op.drop_column("sanatorium_reviews", "appeal_status")
    op.drop_column("sanatorium_reviews", "replied_by_user_id")
    op.drop_column("sanatorium_reviews", "replied_at")
    op.drop_column("sanatorium_reviews", "reply_status")
    op.drop_column("sanatorium_reviews", "reply_language")
    op.drop_column("sanatorium_reviews", "reply_body")
    op.drop_column("sanatorium_reviews", "photos")
    op.drop_column("sanatorium_reviews", "negative_tags")
    op.drop_column("sanatorium_reviews", "positive_tags")
    op.drop_column("sanatorium_reviews", "translated_body")
    op.drop_column("sanatorium_reviews", "score_label")
    op.drop_column("sanatorium_reviews", "stayed_room_name")
    op.drop_column("sanatorium_reviews", "stayed_at")
    op.drop_column("sanatorium_reviews", "language")
    op.drop_column("sanatorium_reviews", "reviewer_avatar_url")
    op.drop_column("sanatorium_reviews", "external_url")
    op.drop_column("sanatorium_reviews", "external_id")
    op.drop_column("sanatorium_reviews", "source")
    op.drop_column("sanatorium_reviews", "room_id")
    op.drop_column("sanatorium_reviews", "booking_id")
