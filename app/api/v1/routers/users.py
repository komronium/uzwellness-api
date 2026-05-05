import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import CurrentUser, require_roles
from app.models.user import User, UserRole
from app.schemas.user import UserList, UserRead, UserUpdate
from app.services.user_service import UserService, get_user_service

router = APIRouter(prefix="/users", tags=["users"])

require_super_admin = require_roles(UserRole.SUPER_ADMIN)


@router.get("/me", response_model=UserRead)
async def get_me(current_user: CurrentUser) -> UserRead:
    return UserRead.model_validate(current_user)


@router.get("", response_model=UserList)
async def list_users(
    _: User = Depends(require_super_admin),
    users: UserService = Depends(get_user_service),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    role: UserRole | None = Query(default=None),
) -> UserList:
    items, total = await users.list_users(limit=limit, offset=offset, role=role)
    return UserList(
        items=[UserRead.model_validate(u) for u in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{user_id}", response_model=UserRead)
async def get_user(
    user_id: uuid.UUID,
    _: User = Depends(require_super_admin),
    users: UserService = Depends(get_user_service),
) -> UserRead:
    user = await users.get_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return UserRead.model_validate(user)


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    _: User = Depends(require_super_admin),
    users: UserService = Depends(get_user_service),
) -> UserRead:
    user = await users.get_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    updated = await users.update(user, payload)
    return UserRead.model_validate(updated)
