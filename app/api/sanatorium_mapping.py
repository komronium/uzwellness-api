from collections.abc import Sequence
from typing import TypeVar

from app.models.sanatorium import Sanatorium
from app.models.user import User, UserRole
from app.schemas.sanatorium import (
    SanatoriumAdminList,
    SanatoriumAdminRead,
    SanatoriumList,
    SanatoriumRead,
)

_Read = TypeVar("_Read", SanatoriumRead, SanatoriumAdminRead)


def _sees_commercial_terms(viewer: User | None, sanatorium: Sanatorium) -> bool:
    """Commissions and the owning admin are visible to the platform and owner."""
    if viewer is None:
        return False
    if viewer.role == UserRole.SUPER_ADMIN:
        return True
    return viewer.role == UserRole.ADMIN and sanatorium.admin_user_id == viewer.id


def _sees_agent_tiers(viewer: User | None, sanatorium: Sanatorium) -> bool:
    """Agents are priced off the tiers, so they may read them too."""
    if viewer is not None and viewer.role == UserRole.AGENT:
        return True
    return _sees_commercial_terms(viewer, sanatorium)


def _redact(read: _Read, sanatorium: Sanatorium, viewer: User | None) -> _Read:
    if not _sees_commercial_terms(viewer, sanatorium):
        read.admin_user_id = None
        read.platform_commission_percent = None
        read.b2b_commission_percent = None
    if not _sees_agent_tiers(viewer, sanatorium):
        read.agent_discount_tiers = []
    return read


def sanatorium_public_read(
    sanatorium: Sanatorium, *, locale: str, viewer: User | None
) -> SanatoriumRead:
    return _redact(SanatoriumRead.from_obj(sanatorium, locale), sanatorium, viewer)


def sanatorium_admin_read(
    sanatorium: Sanatorium, *, viewer: User | None
) -> SanatoriumAdminRead:
    return _redact(SanatoriumAdminRead.model_validate(sanatorium), sanatorium, viewer)


def sanatorium_list(
    sanatoriums: Sequence[Sanatorium],
    *,
    total: int,
    limit: int,
    offset: int,
    locale: str,
    viewer: User | None,
) -> SanatoriumList:
    return SanatoriumList(
        items=[
            sanatorium_public_read(sanatorium, locale=locale, viewer=viewer)
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
    viewer: User | None,
) -> SanatoriumAdminList:
    return SanatoriumAdminList(
        items=[
            sanatorium_admin_read(sanatorium, viewer=viewer)
            for sanatorium in sanatoriums
        ],
        total=total,
        limit=limit,
        offset=offset,
    )
