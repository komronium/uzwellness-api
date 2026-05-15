import uuid
from datetime import UTC, datetime

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import create_token, decode_token
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.auth import Token
from app.schemas.user import UserCreate
from app.services.user_service import UserService, get_user_service


class AuthService:
    def __init__(self, users: UserService, db: AsyncSession) -> None:
        self.users = users
        self.db = db

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
        return await self._issue_token_pair(user.id)

    async def refresh(self, refresh_token: str) -> Token:
        user_id, jti = self._parse_refresh_token(refresh_token)
        record = await self.db.get(RefreshToken, jti)
        if record is None or record.revoked or record.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token revoked or invalid",
            )
        if record.expires_at < datetime.now(UTC):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token expired",
            )

        user = await self.users.get_by_id(user_id)
        if user is None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive",
            )

        record.revoked = True
        return await self._issue_token_pair(user.id, commit=True)

    async def _issue_token_pair(
        self, user_id: uuid.UUID, *, commit: bool = True
    ) -> Token:
        subject = str(user_id)
        access_token, _ = create_token(subject, "access")
        refresh_jti = uuid.uuid4()
        refresh_token, expires_at = create_token(
            subject, "refresh", jti=str(refresh_jti)
        )
        self.db.add(
            RefreshToken(id=refresh_jti, user_id=user_id, expires_at=expires_at)
        )
        if commit:
            await self.db.commit()
        return Token(access_token=access_token, refresh_token=refresh_token)

    @staticmethod
    def _parse_refresh_token(token: str) -> tuple[uuid.UUID, uuid.UUID]:
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
            user_id = uuid.UUID(claims["sub"])
            jti = uuid.UUID(claims["jti"])
        except (KeyError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token subject",
            ) from exc
        return user_id, jti


def get_auth_service(
    users: UserService = Depends(get_user_service),
    db: AsyncSession = Depends(get_db),
) -> AuthService:
    return AuthService(users, db)
