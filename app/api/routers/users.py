import uuid

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, not_found, require_roles
from app.core.pagination import LargePagination
from app.models.user import User, UserRole
from app.schemas.user import UserAdminCreate, UserList, UserRead, UserUpdate
from app.services.user_service import UserService, get_user_service

router = APIRouter(prefix="/users", tags=["users"])

require_super_admin = require_roles(UserRole.SUPER_ADMIN)


@router.get("/me", response_model=UserRead)
async def get_me(
    current_user: CurrentUser,
    users: UserService = Depends(get_user_service),
) -> UserRead:
    return await users.to_read(current_user)


@router.post(
    "",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_user(
    payload: UserAdminCreate,
    _: User = Depends(require_super_admin),
    users: UserService = Depends(get_user_service),
) -> UserRead:
    user = await users.create_by_admin(payload)
    return await users.to_read(user)


@router.get("", response_model=UserList)
async def list_users(
    page: LargePagination,
    _: User = Depends(require_super_admin),
    users: UserService = Depends(get_user_service),
    role: UserRole | None = Query(default=None),
) -> UserList:
    items, total = await users.list_users(
        limit=page.limit, offset=page.offset, role=role
    )
    return UserList(
        items=await users.to_read_bulk(items),
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/{user_id}", response_model=UserRead)
async def get_user(
    user_id: uuid.UUID,
    _: User = Depends(require_super_admin),
    users: UserService = Depends(get_user_service),
) -> UserRead:
    user = await users.get_by_id(user_id)
    if user is None:
        raise not_found("User not found")
    return await users.to_read(user)


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    _: User = Depends(require_super_admin),
    users: UserService = Depends(get_user_service),
) -> UserRead:
    user = await users.get_by_id(user_id)
    if user is None:
        raise not_found("User not found")
    updated = await users.update(user, payload)
    return await users.to_read(updated)
