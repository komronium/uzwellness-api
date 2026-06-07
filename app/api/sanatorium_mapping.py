from collections.abc import Sequence

from app.models.sanatorium import Sanatorium
from app.schemas.sanatorium import (
    SanatoriumAdminList,
    SanatoriumAdminRead,
    SanatoriumList,
    SanatoriumRead,
)


def sanatorium_public_read(sanatorium: Sanatorium, *, locale: str) -> SanatoriumRead:
    return SanatoriumRead.from_obj(sanatorium, locale)


def sanatorium_admin_read(sanatorium: Sanatorium) -> SanatoriumAdminRead:
    return SanatoriumAdminRead.model_validate(sanatorium)


def sanatorium_list(
    sanatoriums: Sequence[Sanatorium],
    *,
    total: int,
    limit: int,
    offset: int,
    locale: str,
) -> SanatoriumList:
    return SanatoriumList(
        items=[
            sanatorium_public_read(sanatorium, locale=locale)
            for sanatorium in sanatoriums
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


def sanatorium_admin_list(
    sanatoriums: Sequence[Sanatorium],
    *,
    total: int,
    limit: int,
    offset: int,
) -> SanatoriumAdminList:
    return SanatoriumAdminList(
        items=[sanatorium_admin_read(sanatorium) for sanatorium in sanatoriums],
        total=total,
        limit=limit,
        offset=offset,
    )
