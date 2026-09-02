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
            # The field name stays in the sentence: the admin UI maps it back
            # to the form control the operator has to fix.
            detail=(
                f"{field} {value} does not match any "
                f"{field.removesuffix('_id').replace('_', ' ')}"
            ),
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
    unique_ids = list(dict.fromkeys(ids))
    rows = (await db.scalars(select(model).where(model.id.in_(unique_ids)))).all()
    by_id = {row.id: row for row in rows}
    missing = [str(item_id) for item_id in unique_ids if item_id not in by_id]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No {label} found with id: {', '.join(missing)}",
        )
    return [by_id[item_id] for item_id in unique_ids]


async def lock_rows(db: AsyncSession, model: type[T], ids) -> None:
    """Take a row lock on `ids`, in id order, without loading the rows.

    Writers that touch the same child rows — a guest booking nights and an
    admin blocking the same dates — otherwise race to INSERT the same
    (room, date) pair and one of them loses to a unique constraint. Locking
    the parent first makes them queue instead. The ORDER BY is what keeps two
    callers holding different subsets from deadlocking.
    """

    wanted = sorted(set(ids))
    if not wanted:
        return
    await db.execute(
        select(model.id)
        .where(model.id.in_(wanted))
        .order_by(model.id)
        .with_for_update()
    )
