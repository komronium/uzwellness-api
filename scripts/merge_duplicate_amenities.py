"""Merge the old English-only seed amenities into the translated catalog rows.

The seed catalog (coded rows, English text copied into uz/ru) and the admin
catalog (no code, real uz/ru names) ended up describing the same services, so
guests saw both. For each pair the translated row survives, inherits the code,
and takes over every sanatorium / room / rate plan / program link; the seed row
is then deleted. It also fills in uz/ru for seed rows that have no twin.

Usage:
    uv run python -m scripts.merge_duplicate_amenities
    uv run python -m scripts.merge_duplicate_amenities --write

Without --write the script only reports what it would do and rolls back.
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SessionLocal

# seed code -> (category, English name) of the translated row that survives.
MERGES: dict[str, tuple[str, str]] = {
    "doctor_consultation": ("medical", "Doctor supervision"),
    "lab_diagnostics": ("medical", "Laboratory"),
    "physiotherapy": ("medical", "Physiotherapy"),
    "mineral_water": ("medical", "Mineral water"),
    "pool_access": ("wellness", "Pool"),
    "sauna": ("wellness", "Sauna"),
    "parking": ("transport", "Parking"),
    "wifi": ("connectivity", "Wi-Fi"),
    "kids_corner": ("family", "Kids club"),
}

# Seed rows with no twin: only their uz/ru text was missing.
TRANSLATIONS: dict[str, tuple[str, str]] = {
    "diet_meals": ("Parhez ovqatlanish", "Диетическое питание"),
    "mountain_air": ("Tog' havosi", "Горный воздух"),
    "garden": ("Sayr qilish bog'i", "Парк для прогулок"),
    "therapeutic_baths": ("Davolovchi vannalar", "Лечебные ванны"),
    "transfer": ("Transfer xizmati", "Трансфер"),
}

# link table -> column that, together with amenity_id, is its primary key.
LINK_TABLES = {
    "sanatorium_amenities": "sanatorium_id",
    "room_amenities": "room_id",
    "rate_plan_amenities": "rate_plan_id",
    "program_amenities": "program_id",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Persist changes. Without this flag the script rolls back.",
    )
    return parser.parse_args()


async def merge(db: AsyncSession) -> None:
    for code, (category, name_en) in MERGES.items():
        source = (
            await db.execute(
                text(
                    "SELECT id, display_order, name->>'en' AS name_en, category "
                    "FROM amenities WHERE code = :code"
                ),
                {"code": code},
            )
        ).first()
        targets = (
            await db.execute(
                text(
                    "SELECT id FROM amenities WHERE code IS NULL "
                    "AND category = :category AND name->>'en' = :name"
                ),
                {"category": category, "name": name_en},
            )
        ).all()
        if source is None or (source.category, source.name_en) == (category, name_en):
            print(f"{code}: already merged, skipping")
            continue
        if len(targets) != 1:
            raise SystemExit(
                f"{code}: expected exactly one target '{name_en}', found {len(targets)}"
            )
        target_id = targets[0].id

        for table, owner in LINK_TABLES.items():
            moved = await db.execute(
                text(
                    f"UPDATE {table} t SET amenity_id = :target "
                    f"WHERE t.amenity_id = :source AND NOT EXISTS ("
                    f"SELECT 1 FROM {table} x "
                    f"WHERE x.{owner} = t.{owner} AND x.amenity_id = :target)"
                ),
                {"source": source.id, "target": target_id},
            )
            print(f"{code}: {table} re-pointed {moved.rowcount}")

        # The code is unique, so free it before the target takes it over.
        await db.execute(
            text("DELETE FROM amenities WHERE id = :id"), {"id": source.id}
        )
        await db.execute(
            text(
                "UPDATE amenities SET code = :code, display_order = :o WHERE id = :id"
            ),
            {"code": code, "o": source.display_order, "id": target_id},
        )

    for code, (uz, ru) in TRANSLATIONS.items():
        result = await db.execute(
            text(
                "UPDATE amenities SET name = name || "
                "jsonb_build_object('uz', CAST(:uz AS text), 'ru', CAST(:ru AS text)) "
                "WHERE code = :code"
            ),
            {"code": code, "uz": uz, "ru": ru},
        )
        print(f"{code}: translated {result.rowcount}")


async def main() -> None:
    args = parse_args()
    async with SessionLocal() as db:
        await merge(db)
        if args.write:
            await db.commit()
            print("Done.")
        else:
            await db.rollback()
            print("Dry run complete; rolled back.")


if __name__ == "__main__":
    asyncio.run(main())
