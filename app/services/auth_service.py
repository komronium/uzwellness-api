import uuid

from fastapi import Depends, HTTPException, status

from app.core.security import create_token, decode_token
from app.models.user import User
from app.schemas.auth import Token
from app.schemas.user import UserCreate
from app.services.user_service import UserService, get_user_service


class AuthService:
    def __init__(self, users: UserService) -> None:
        self.users = users

    async def register(self, payload: UserCreate) -> User:
        if await self.users.get_by_email(payload.email) is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            )
        return await self.users.create(payload)

    async def login(self, email: str, password: str) -> Token:
        user = await self.users.authenticate(email, password)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )
        return self._issue_token_pair(user.id)

    async def refresh(self, refresh_token: str) -> Token:
        user_id = self._parse_refresh_token(refresh_token)
        user = await self.users.get_by_id(user_id)
        if user is None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive",
            )
        return self._issue_token_pair(user.id)

    @staticmethod
    def _issue_token_pair(user_id: uuid.UUID) -> Token:
        subject = str(user_id)
        return Token(
            access_token=create_token(subject, "access"),
            refresh_token=create_token(subject, "refresh"),
        )

    @staticmethod
    def _parse_refresh_token(token: str) -> uuid.UUID:
        try:
            claims = decode_token(token)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
            ) from exc

        if claims.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Wrong token type",
            )

        try:
            return uuid.UUID(claims["sub"])
        except (KeyError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token subject",
            ) from exc


def get_auth_service(
    users: UserService = Depends(get_user_service),
) -> AuthService:
    return AuthService(users)
