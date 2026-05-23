import re
import unicodedata
import uuid
from typing import TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base

_UZBEK_STRIP = str.maketrans({"ʻ": "", "ʼ": "", "’": "", "'": ""})


def slugify(text: str, *, fallback: str = "item") -> str:
    text = text.translate(_UZBEK_STRIP)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return text or fallback


T = TypeVar("T", bound=Base)


async def resolve_unique_slug(
    db: AsyncSession,
    model: type[T],
    base: str,
    *,
    exclude_id: uuid.UUID | None = None,
) -> str:
    """Return `base` if free, otherwise `base-2`, `base-3`, … until unique.

    `model.slug` must be a column on the given SQLAlchemy model.
    """
    candidate = base
    suffix = 2
    while True:
        existing = await db.scalar(select(model).where(model.slug == candidate))
        if existing is None or existing.id == exclude_id:
            return candidate
        candidate = f"{base}-{suffix}"
        suffix += 1
