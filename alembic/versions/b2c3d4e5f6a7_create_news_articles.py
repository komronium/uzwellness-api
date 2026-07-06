"""create news_articles table

Revision ID: b2c3d4e5f6a7
Revises: 1fff788cc7e0
Create Date: 2026-07-06

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "1fff788cc7e0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "news_articles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("title", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "excerpt",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "body",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "category",
            sa.Enum(
                "guide",
                "health",
                "platform",
                "destinations",
                name="newscategory",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("image_url", sa.String(length=500), nullable=True),
        sa.Column(
            "is_published",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
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
    op.create_index(
        op.f("ix_news_articles_slug"), "news_articles", ["slug"], unique=True
    )
    op.create_index(
        op.f("ix_news_articles_category"), "news_articles", ["category"], unique=False
    )
    op.create_index(
        op.f("ix_news_articles_is_published"),
        "news_articles",
        ["is_published"],
        unique=False,
    )
    op.create_index(
        op.f("ix_news_articles_published_at"),
        "news_articles",
        ["published_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_news_articles_published_at"), table_name="news_articles")
    op.drop_index(op.f("ix_news_articles_is_published"), table_name="news_articles")
    op.drop_index(op.f("ix_news_articles_category"), table_name="news_articles")
    op.drop_index(op.f("ix_news_articles_slug"), table_name="news_articles")
    op.drop_table("news_articles")
