import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sanatorium import Sanatorium
from app.models.user import User, UserRole


async def assert_sanatorium_access(
    db: AsyncSession,
    sanatorium_id: uuid.UUID,
    user: User,
    *,
    action: str = "manage this sanatorium",
) -> Sanatorium:
    sanatorium = (
        await db.execute(select(Sanatorium).where(Sanatorium.id == sanatorium_id))
    ).scalar_one_or_none()
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
