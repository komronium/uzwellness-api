import uuid
from collections.abc import Sequence

from fastapi import Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import hash_password, verify_password
from app.models.sanatorium import Sanatorium
from app.models.user import User, UserRole
from app.schemas.user import UserAdminCreate, UserCreate, UserUpdate


class UserService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_email(self, email: str) -> User | None:
        result = await self.db.execute(
            select(User).where(User.email == email.lower())
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return await self.db.get(User, user_id)

    async def create(
        self,
        user_in: UserCreate,
        role: UserRole = UserRole.CUSTOMER,
    ) -> User:
        user = User(
            email=user_in.email.lower(),
            password_hash=hash_password(user_in.password),
            role=role,
            full_name=user_in.full_name,
            phone=user_in.phone,
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def create_by_admin(self, payload: UserAdminCreate) -> User:
        if await self.get_by_email(payload.email) is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            )
        if payload.sanatorium_id is not None:
            exists = (
                await self.db.execute(
                    select(Sanatorium.id).where(Sanatorium.id == payload.sanatorium_id)
                )
            ).scalar_one_or_none()
            if exists is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Sanatorium not found",
                )
        user = User(
            email=payload.email.lower(),
            password_hash=hash_password(payload.password),
            role=payload.role,
            full_name=payload.full_name,
            phone=payload.phone,
            sanatorium_id=payload.sanatorium_id,
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def authenticate(self, email: str, password: str) -> User | None:
        user = await self.get_by_email(email)
        if user is None or not user.is_active:
            return None
        if not verify_password(password, user.password_hash):
            return None
        return user

    async def list_users(
        self,
        *,
        limit: int,
        offset: int,
        role: UserRole | None = None,
    ) -> tuple[Sequence[User], int]:
        base = select(User)
        if role is not None:
            base = base.where(User.role == role)

        total_stmt = select(func.count()).select_from(base.subquery())
        total = (await self.db.execute(total_stmt)).scalar_one()

        stmt = base.order_by(User.created_at.desc()).limit(limit).offset(offset)
        rows = (await self.db.execute(stmt)).scalars().all()
        return rows, total

    async def update(self, user: User, payload: UserUpdate) -> User:
        data = payload.model_dump(exclude_unset=True)
        if data.get("sanatorium_id") is not None:
            exists = (await self.db.execute(
                select(Sanatorium.id).where(Sanatorium.id == data["sanatorium_id"])
            )).scalar_one_or_none()
            if exists is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Sanatorium not found",
                )
        for field, value in data.items():
            setattr(user, field, value)
        await self.db.commit()
        await self.db.refresh(user)
        return user


def get_user_service(db: AsyncSession = Depends(get_db)) -> UserService:
    return UserService(db)
