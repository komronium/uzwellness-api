from fastapi import APIRouter, Depends, status

from app.schemas.auth import LoginRequest, RefreshRequest, Token
from app.schemas.user import UserCreate, UserRead
from app.services.auth_service import AuthService, get_auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    payload: UserCreate,
    auth: AuthService = Depends(get_auth_service),
) -> UserRead:
    user = await auth.register(payload)
    return UserRead.model_validate(user)


@router.post("/login", response_model=Token)
async def login(
    payload: LoginRequest,
    auth: AuthService = Depends(get_auth_service),
) -> Token:
    return await auth.login(payload.email, payload.password)


@router.post("/refresh", response_model=Token)
async def refresh(
    payload: RefreshRequest,
    auth: AuthService = Depends(get_auth_service),
) -> Token:
    return await auth.refresh(payload.refresh_token)
