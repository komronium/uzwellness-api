import uuid
from typing import TypeVar

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base

T = TypeVar("T", bound=Base)


async def assert_fk(
    db: AsyncSession,
    model: type[T],
    value: uuid.UUID | None,
    field: str,
) -> None:
    if value is None:
        return
    found = await db.scalar(select(model.id).where(model.id == value))
    if found is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field} not found",
        )


async def fetch_by_ids(
    db: AsyncSession,
    model: type[T],
    ids: list[uuid.UUID],
    *,
    label: str,
) -> list[T]:
    """Load every row matching `ids` or raise 400 if any are missing.

    `label` names the resource for the error message (e.g. "amenity").
    """
    if not ids:
        return []
    rows = (await db.scalars(select(model).where(model.id.in_(ids)))).all()
    if len(rows) != len(ids):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"One or more {label} IDs not found",
        )
    return list(rows)
