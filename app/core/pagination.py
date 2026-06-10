from collections.abc import Sequence
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Query
from sqlalchemy import Select, func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(slots=True)
class PaginationParams:
    limit: int
    offset: int


def pagination_params(
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaginationParams:
    return PaginationParams(limit=limit, offset=offset)


def large_pagination_params(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaginationParams:
    return PaginationParams(limit=limit, offset=offset)


Pagination = Annotated[PaginationParams, Depends(pagination_params)]
LargePagination = Annotated[PaginationParams, Depends(large_pagination_params)]


async def count_query(db: AsyncSession, stmt: Select) -> int:
    """Total row count of a statement, ignoring its ordering and selected columns."""
    count_subquery = (
        stmt.order_by(None)
        .with_only_columns(literal_column("1"), maintain_column_froms=True)
        .subquery()
    )
    total = await db.scalar(select(func.count()).select_from(count_subquery))
    return total or 0


async def paginated(
    db: AsyncSession, stmt: Select, *, limit: int, offset: int
) -> tuple[Sequence[Any], int]:
    total = await count_query(db, stmt)
    rows = (await db.scalars(stmt.limit(limit).offset(offset))).all()
    return rows, total
