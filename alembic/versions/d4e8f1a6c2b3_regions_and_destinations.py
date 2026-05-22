"""regions (14 viloyatlar) and destinations (homepage tiles) — split entities

Revision ID: d4e8f1a6c2b3
Revises: 3132bf292c7d
Create Date: 2026-05-22 14:00:00.000000

Two separate entities for two separate concerns:

- `regions` is the fixed catalog of 14 administrative viloyatlar. Admin
  picks one when creating a sanatorium. Used for filtering and as a
  natural geographic grouping.
- `destinations` is the curated homepage tile feed (6 to start: Tashkent
  Region, Chimgan Mountains, Samarkand, Zaamin, Boysun, Fergana Valley).
  Each sanatorium belongs to at most one destination (its featured tile).
  A tile can still gather sanatoriums from any subset — that's just a
  nullable FK from sanatoriums.destination_id.

Backfill: `sanatoriums.region_id` is filled by best-effort city ILIKE
against viloyat patterns. `sanatoriums.destination_id` is similarly
backfilled but in reverse iteration order so specific patterns
(Chimgan → Charvak) win over the catch-all (Tashkent Region). Legacy
free-form `region` string column is dropped.

There's no display_order column: list endpoints order by `created_at
ASC`, so insertion order in this migration becomes the implicit display
order. The SEED_DESTINATIONS list is therefore ordered to match the FE
homepage tile layout.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d4e8f1a6c2b3"
down_revision: Union[str, None] = "3132bf292c7d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (slug, name_uz, name_ru, name_en, city_patterns)
# Insertion order = list order = FE dropdown order (alphabetical EN, with
# Tashkent City + Tashkent Region grouped first, Karakalpakstan last).
SEED_REGIONS = [
    (
        "toshkent-shahri",
        "Toshkent shahri",
        "Город Ташкент",
        "Tashkent City",
        ["toshkent shahri", "tashkent city"],
    ),
    (
        "toshkent",
        "Toshkent viloyati",
        "Ташкентская область",
        "Tashkent Region",
        ["%toshkent%", "%tashkent%"],
    ),
    (
        "andijon",
        "Andijon",
        "Андижанская область",
        "Andijan Region",
        ["%andijon%", "%andijan%"],
    ),
    (
        "buxoro",
        "Buxoro",
        "Бухарская область",
        "Bukhara Region",
        ["%buxoro%", "%bukhara%"],
    ),
    (
        "fargona",
        "Farg'ona",
        "Ферганская область",
        "Fergana Region",
        ["%fargona%", "%fargʻona%", "%fergana%"],
    ),
    (
        "jizzax",
        "Jizzax",
        "Джизакская область",
        "Jizzakh Region",
        ["%jizzax%", "%jizzakh%", "%zaamin%", "%zomin%"],
    ),
    (
        "xorazm",
        "Xorazm",
        "Хорезмская область",
        "Khorezm Region",
        ["%xorazm%", "%khorezm%", "%urganch%", "%xiva%", "%khiva%"],
    ),
    (
        "namangan",
        "Namangan",
        "Наманганская область",
        "Namangan Region",
        ["%namangan%"],
    ),
    (
        "navoiy",
        "Navoiy",
        "Навоийская область",
        "Navoiy Region",
        ["%navoiy%", "%navoi%"],
    ),
    (
        "qashqadaryo",
        "Qashqadaryo",
        "Кашкадарьинская область",
        "Qashqadaryo Region",
        ["%qashqadaryo%", "%kashkadarya%", "%qarshi%"],
    ),
    (
        "samarqand",
        "Samarqand",
        "Самаркандская область",
        "Samarkand Region",
        ["%samarqand%", "%samarkand%"],
    ),
    (
        "sirdaryo",
        "Sirdaryo",
        "Сырдарьинская область",
        "Sirdaryo Region",
        ["%sirdaryo%", "%syrdarya%"],
    ),
    (
        "surxondaryo",
        "Surxondaryo",
        "Сурхандарьинская область",
        "Surkhandaryo Region",
        ["%surxondaryo%", "%surkhandarya%", "%termiz%", "%boysun%", "%baysun%"],
    ),
    (
        "qoraqalpogiston",
        "Qoraqalpog'iston",
        "Каракалпакстан",
        "Karakalpakstan",
        ["%qoraqalpog%", "%karakalpak%", "%nukus%"],
    ),
]


# (slug, name_uz, name_ru, name_en, tagline_uz, tagline_ru, tagline_en,
#  lat, lng, city_patterns)
# Insertion order = FE homepage tile order. Backfill iterates in reverse
# so the most specific city_patterns (Fergana Valley first, etc.) match
# before the generic Tashkent catch-all.
SEED_DESTINATIONS = [
    (
        "tashkent-region",
        "Toshkent",
        "Ташкент",
        "Tashkent Region",
        "Poytaxt yaqinidagi zamonaviy spa-kurortlar",
        "Современные спа-курорты рядом со столицей",
        "Modern spa resorts near the capital",
        "41.3111", "69.2797",
        ["%toshkent%", "%tashkent%"],
    ),
    (
        "chimgan-mountains",
        "Chimgan tog'lari",
        "Чимганские горы",
        "Chimgan Mountains",
        "Alp havosi va qish mavsumida wellness",
        "Альпийский воздух и зимний wellness",
        "Alpine air and ski-season wellness",
        "41.5500", "70.0167",
        ["%chimgan%", "%chimgʻon%", "%charvak%", "%bostanliq%", "%bostanlyk%"],
    ),
    (
        "samarkand",
        "Samarqand",
        "Самарканд",
        "Samarkand",
        "Hashamatli sanatoriyalar bilan tarixiy shahar",
        "Исторический город с люксовыми санаториями",
        "Heritage city with luxury sanatoriums",
        "39.6542", "66.9597",
        ["%samarqand%", "%samarkand%"],
    ),
    (
        "zaamin-national-park",
        "Zomin milliy bog'i",
        "Зааминский нацпарк",
        "Zaamin National Park",
        "Qarag'ay o'rmonlari va baland tog' terapiyasi",
        "Сосновые леса и высотная терапия",
        "Pine forests and altitude therapy",
        "39.9500", "68.4000",
        ["%zaamin%", "%zomin%"],
    ),
    (
        "boysun",
        "Boysun",
        "Байсун",
        "Boysun",
        "YuNESKO ro'yxatidagi madaniy shifo",
        "ЮНЕСКО-наследие и культурное оздоровление",
        "UNESCO-listed cultural healing",
        "38.2000", "67.2000",
        ["%boysun%", "%baysun%"],
    ),
    (
        "fergana-valley",
        "Farg'ona vodiysi",
        "Ферганская долина",
        "Fergana Valley",
        "Issiq buloqlar va an'anaviy tabobat",
        "Горячие источники и народная медицина",
        "Hot springs and traditional medicine",
        "40.3892", "71.7833",
        ["%fargona%", "%fargʻona%", "%fergana%", "%namangan%", "%andijon%", "%andijan%"],
    ),
]


def upgrade() -> None:
    # ── regions (14 viloyatlar) ────────────────────────────────────────────
    op.create_table(
        "regions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column(
            "name",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
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
    op.create_index(op.f("ix_regions_slug"), "regions", ["slug"], unique=True)
    op.create_index(op.f("ix_regions_is_active"), "regions", ["is_active"])

    for slug, n_uz, n_ru, n_en, _patterns in SEED_REGIONS:
        op.execute(
            sa.text(
                """
                INSERT INTO regions (id, slug, name, is_active)
                VALUES (
                    gen_random_uuid(), :slug,
                    jsonb_build_object('uz', :n_uz, 'ru', :n_ru, 'en', :n_en),
                    TRUE
                )
                """
            ).bindparams(slug=slug, n_uz=n_uz, n_ru=n_ru, n_en=n_en)
        )

    # ── destinations (marketing tiles) ─────────────────────────────────────
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
        sa.Column("hero_image", sa.String(length=500), nullable=True),
        sa.Column(
            "country",
            sa.String(length=80),
            nullable=False,
            server_default="Uzbekistan",
        ),
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
    op.create_index(
        op.f("ix_destinations_slug"), "destinations", ["slug"], unique=True
    )
    op.create_index(
        op.f("ix_destinations_is_active"), "destinations", ["is_active"]
    )

    for (
        slug, n_uz, n_ru, n_en, t_uz, t_ru, t_en, lat, lng, _patterns,
    ) in SEED_DESTINATIONS:
        op.execute(
            sa.text(
                """
                INSERT INTO destinations
                    (id, slug, name, tagline, description, country,
                     lat, lng, is_active)
                VALUES
                    (gen_random_uuid(), :slug,
                     jsonb_build_object('uz', :n_uz, 'ru', :n_ru, 'en', :n_en),
                     jsonb_build_object('uz', :t_uz, 'ru', :t_ru, 'en', :t_en),
                     '{}'::jsonb,
                     'Uzbekistan',
                     CAST(:lat AS NUMERIC(9,6)),
                     CAST(:lng AS NUMERIC(9,6)),
                     TRUE)
                """
            ).bindparams(
                slug=slug, n_uz=n_uz, n_ru=n_ru, n_en=n_en,
                t_uz=t_uz, t_ru=t_ru, t_en=t_en,
                lat=lat, lng=lng,
            )
        )

    # ── sanatoriums.region_id + destination_id ─────────────────────────────
    op.add_column(
        "sanatoriums",
        sa.Column("region_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "sanatoriums",
        sa.Column("destination_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_sanatoriums_region_id_regions"),
        "sanatoriums",
        "regions",
        ["region_id"],
        ["id"],
        ondelete="SET NULL",
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
        op.f("ix_sanatoriums_region_id"), "sanatoriums", ["region_id"]
    )
    op.create_index(
        op.f("ix_sanatoriums_destination_id"),
        "sanatoriums",
        ["destination_id"],
    )

    # Backfill region_id: iterate seed in reverse so specific patterns
    # (Jizzax → zomin) win over the generic Toshkent catch-all.
    for slug, _u, _r, _e, patterns in reversed(SEED_REGIONS):
        params: dict[str, str] = {"slug": slug}
        likes: list[str] = []
        for idx, p in enumerate(patterns):
            key = f"p{idx}"
            params[key] = p
            likes.append(f"LOWER(s.city) LIKE :{key}")
        where = " OR ".join(likes)
        op.execute(
            sa.text(
                f"""
                UPDATE sanatoriums s
                   SET region_id = r.id
                  FROM regions r
                 WHERE r.slug = :slug
                   AND s.region_id IS NULL
                   AND ({where})
                """
            ).bindparams(**params)
        )

    # Backfill destination_id: iterate reverse so specific tiles
    # (Fergana Valley first match — namangan/andijon — before
    # Tashkent catch-all) win.
    for slug, *_, patterns in reversed(SEED_DESTINATIONS):
        params = {"slug": slug}
        likes = []
        for idx, p in enumerate(patterns):
            key = f"p{idx}"
            params[key] = p
            likes.append(f"LOWER(s.city) LIKE :{key}")
        where = " OR ".join(likes)
        op.execute(
            sa.text(
                f"""
                UPDATE sanatoriums s
                   SET destination_id = d.id
                  FROM destinations d
                 WHERE d.slug = :slug
                   AND s.destination_id IS NULL
                   AND ({where})
                """
            ).bindparams(**params)
        )

    # Drop the legacy free-form region string column.
    op.drop_index("ix_sanatoriums_region", table_name="sanatoriums")
    op.drop_column("sanatoriums", "region")


def downgrade() -> None:
    op.add_column(
        "sanatoriums",
        sa.Column("region", sa.String(length=120), nullable=True),
    )
    op.create_index(
        "ix_sanatoriums_region", "sanatoriums", ["region"], unique=False
    )
    op.execute(
        """
        UPDATE sanatoriums s
           SET region = r.name->>'en'
          FROM regions r
         WHERE s.region_id = r.id
        """
    )

    op.drop_index(
        op.f("ix_sanatoriums_destination_id"), table_name="sanatoriums"
    )
    op.drop_index(op.f("ix_sanatoriums_region_id"), table_name="sanatoriums")
    op.drop_constraint(
        op.f("fk_sanatoriums_destination_id_destinations"),
        "sanatoriums",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_sanatoriums_region_id_regions"),
        "sanatoriums",
        type_="foreignkey",
    )
    op.drop_column("sanatoriums", "destination_id")
    op.drop_column("sanatoriums", "region_id")

    op.drop_index(op.f("ix_destinations_is_active"), table_name="destinations")
    op.drop_index(op.f("ix_destinations_slug"), table_name="destinations")
    op.drop_table("destinations")

    op.drop_index(op.f("ix_regions_is_active"), table_name="regions")
    op.drop_index(op.f("ix_regions_slug"), table_name="regions")
    op.drop_table("regions")
