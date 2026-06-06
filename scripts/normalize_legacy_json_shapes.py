"""Normalize legacy JSONB payloads to the current API schema.

Run from the project root:
    uv run python scripts/normalize_legacy_json_shapes.py --dry-run
    uv run python scripts/normalize_legacy_json_shapes.py --write
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@dataclass
class ChangeStats:
    rooms_seen: int = 0
    rooms_changed: int = 0
    reviews_seen: int = 0
    reviews_changed: int = 0


def normalize_room_features(value: Any) -> Any:
    if not isinstance(value, dict):
        return value

    data = dict(value)

    bathroom = data.get("bathroom")
    if isinstance(bathroom, str):
        bathroom_value = bathroom.strip().lower()
        if bathroom_value in {"private", "private_bathroom", "ensuite"}:
            data["bathroom"] = {"private": True}
        elif bathroom_value in {"shared", "shared_bathroom"}:
            data["bathroom"] = {"private": False}

    windows = data.pop("windows", None)
    if "has_window" not in data and windows is not None:
        if isinstance(windows, bool):
            data["has_window"] = windows
        elif isinstance(windows, str):
            windows_value = windows.strip().lower()
            if windows_value in {"all", "some", "yes", "true", "1"}:
                data["has_window"] = True
            elif windows_value in {"none", "no", "false", "0"}:
                data["has_window"] = False

    if "balcony" in data:
        comfort = data.get("comfort") if isinstance(data.get("comfort"), dict) else {}
        comfort.setdefault("balcony", data.pop("balcony"))
        data["comfort"] = comfort

    if "sitting_area" in data:
        comfort = data.get("comfort") if isinstance(data.get("comfort"), dict) else {}
        comfort.setdefault("sofa", data.pop("sitting_area"))
        data["comfort"] = comfort

    return data


def normalize_beds(value: Any) -> Any:
    if not isinstance(value, list) or not value:
        return value

    if all(_is_flat_bed(item) for item in value):
        return [{"beds": [_normalize_bed(item) for item in value]}]

    return [
        {"beds": [_normalize_bed(item)]} if _is_flat_bed(item) else item
        for item in value
    ]


def normalize_review_photos(value: Any) -> Any:
    if not isinstance(value, list):
        return value
    return [{"url": item} if isinstance(item, str) else item for item in value]


def _is_flat_bed(value: Any) -> bool:
    return isinstance(value, dict) and "type" in value and "beds" not in value


def _normalize_bed(value: dict) -> dict:
    data = dict(value)
    width_cm = data.pop("width_cm", None)
    if width_cm is not None and "size_cm" not in data:
        data["size_cm"] = str(width_cm)
    return data


async def normalize_database(*, write: bool) -> ChangeStats:
    from sqlalchemy import select

    from app.core.database import SessionLocal
    from app.models.review import SanatoriumReview
    from app.models.room import Room

    stats = ChangeStats()
    async with SessionLocal() as db:
        rooms = (await db.scalars(select(Room))).all()
        stats.rooms_seen = len(rooms)
        for room in rooms:
            new_features = normalize_room_features(room.room_features)
            new_beds = normalize_beds(room.beds)
            if new_features != room.room_features or new_beds != room.beds:
                stats.rooms_changed += 1
                if write:
                    room.room_features = new_features
                    room.beds = new_beds

        reviews = (await db.scalars(select(SanatoriumReview))).all()
        stats.reviews_seen = len(reviews)
        for review in reviews:
            new_photos = normalize_review_photos(review.photos)
            if new_photos != review.photos:
                stats.reviews_changed += 1
                if write:
                    review.photos = new_photos

        if write:
            await db.commit()
        else:
            await db.rollback()

    return stats


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Normalize legacy JSONB rows to the current canonical schema."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Report changes only.")
    mode.add_argument("--write", action="store_true", help="Persist changes.")
    return parser.parse_args()


async def async_main() -> None:
    args = parse_args()
    stats = await normalize_database(write=args.write)
    mode = "updated" if args.write else "would update"
    print(f"Rooms scanned: {stats.rooms_seen}; {mode}: {stats.rooms_changed}")
    print(f"Reviews scanned: {stats.reviews_seen}; {mode}: {stats.reviews_changed}")


if __name__ == "__main__":
    asyncio.run(async_main())
