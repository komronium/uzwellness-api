import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sanatorium import Sanatorium
from app.models.user import User, UserRole

SANATORIUM_SUPER_ADMIN_ONLY_FIELDS = frozenset(
    {
        "platform_commission_percent",
        "b2b_commission_percent",
        "agent_discount_tiers",
        "admin_user_id",
        "destination_id",
        "is_featured",
        "display_order",
    }
)


def assert_super_admin_only_fields(
    data: dict, actor: User | None, *, restricted_fields: frozenset[str]
) -> None:
    """Reject the request if a non-super_admin tried to touch privileged fields."""
    if actor is None or actor.role == UserRole.SUPER_ADMIN:
        return
    for field in restricted_fields:
        if field in data:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Only super_admin can modify {field}",
            )


async def assert_sanatorium_access(
    db: AsyncSession,
    sanatorium_id: uuid.UUID,
    user: User,
    *,
    action: str = "manage this sanatorium",
) -> Sanatorium:
    sanatorium = await db.get(Sanatorium, sanatorium_id)
    if sanatorium is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Sanatorium not found"
        )
    if user.role == UserRole.SUPER_ADMIN:
        return sanatorium
    if user.role == UserRole.ADMIN and sanatorium.admin_user_id == user.id:
        return sanatorium
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Not allowed to {action}",
    )
