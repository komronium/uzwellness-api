"""Re-encode legacy PNG/JPEG uploads to WebP and point the DB at them.

Uploads are converted to WebP (<= IMAGE_MAX_DIMENSION px) on the way in, but
older files predate that: treatment-focus tiles alone were 2-2.7 MB PNGs each.
This writes a `.webp` next to each such file (same name, new extension), keeps
the original's owner and mode, and updates the row's URL. Originals are left on
disk so the change can be rolled back; delete them once the site looks right.

360° panoramas and videos are skipped: shrinking a panorama ruins it.

Usage:
    uv run python -m scripts.reencode_images
    uv run python -m scripts.reencode_images --write

Without --write the script only reports what it would do and rolls back.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import text

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.image_processing import to_webp
from app.core.storage import url_to_key

# (table, url column, extra SQL condition for rows that must not be touched)
SOURCES: list[tuple[str, str, str]] = [
    ("treatment_focuses", "image_url", "true"),
    ("packages", "hero_image_url", "true"),
    ("news_articles", "image_url", "true"),
    ("sanatorium_images", "url", "NOT is_360"),
    ("room_images", "url", "NOT is_360 AND NOT is_video"),
]
LEGACY_SUFFIXES = {".png", ".jpg", ".jpeg"}


@dataclass(frozen=True, slots=True)
class Reencoded:
    path: Path
    old_size: int
    new_size: int


def webp_url(url: str) -> str:
    return str(Path(url).with_suffix(".webp"))


def reencode_file(path: Path, *, write: bool) -> Reencoded:
    """Encode `path` as WebP next to it; only writes the file when `write`."""
    content = path.read_bytes()
    webp, _ = to_webp(content)
    target = path.with_suffix(".webp")
    if write:
        tmp = target.with_suffix(".webp.tmp")
        tmp.write_bytes(webp)
        stat = path.stat()
        os.chmod(tmp, stat.st_mode & 0o777)
        try:
            os.chown(tmp, stat.st_uid, stat.st_gid)
        except PermissionError:
            pass  # not root: the file keeps the current user, still readable
        tmp.replace(target)
    return Reencoded(target, len(content), len(webp))


async def run(write: bool) -> None:
    upload_dir = Path(settings.UPLOAD_DIR)
    prefix = settings.UPLOAD_URL_PREFIX.rstrip("/") + "/"
    before = after = count = 0
    async with SessionLocal() as db:
        for table, column, keep in SOURCES:
            rows = (
                await db.execute(
                    text(
                        f"SELECT id, {column} FROM {table} "
                        f"WHERE {column} LIKE :prefix AND {keep}"
                    ),
                    {"prefix": prefix + "%"},
                )
            ).all()
            for row_id, url in rows:
                if Path(url).suffix.lower() not in LEGACY_SUFFIXES:
                    continue
                path = upload_dir / url_to_key(url)
                if not path.is_file():
                    print(f"  missing file, skipped: {table} {row_id} {url}")
                    continue
                result = reencode_file(path, write=write)
                await db.execute(
                    text(f"UPDATE {table} SET {column} = :url WHERE id = :id"),
                    {"url": webp_url(url), "id": row_id},
                )
                count += 1
                before += result.old_size
                after += result.new_size
                print(
                    f"  {table}: {url} {result.old_size // 1024} KB -> "
                    f"{result.new_size // 1024} KB"
                )
        if write:
            await db.commit()
        else:
            await db.rollback()
    action = "Re-encoded" if write else "Dry run (nothing written):"
    print(
        f"{action} {count} image(s), {before / 1_048_576:.1f} MB -> "
        f"{after / 1_048_576:.1f} MB"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write the .webp files and update URLs. Without it nothing changes.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(run(parse_args().write))
