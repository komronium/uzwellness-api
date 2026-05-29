from fastapi import HTTPException, status

from app.core.policies import SanatoriumPolicy
from app.models.sanatorium import Sanatorium
from app.models.user import User


def ensure_can_edit_sanatorium(sanatorium: Sanatorium, user: User) -> None:
    if not SanatoriumPolicy.can_edit(sanatorium, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not allowed to modify this sanatorium",
        )
