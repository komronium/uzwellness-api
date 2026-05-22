import uuid
from collections.abc import Sequence

from fastapi import Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import hash_password, verify_password
from app.models.sanatorium import Sanatorium
from app.models.user import User, UserRole
from app.schemas.user import UserAdminCreate, UserCreate, UserRead, UserUpdate


class UserService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_email(self, email: str) -> User | None:
        result = await self.db.execute(select(User).where(User.email == email.lower()))
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
            self._assert_role_can_own_sanatorium(payload.role)
        user = User(
            email=payload.email.lower(),
            password_hash=hash_password(payload.password),
            role=payload.role,
            full_name=payload.full_name,
            phone=payload.phone,
        )
        self.db.add(user)
        await self.db.flush()
        if payload.sanatorium_id is not None:
            await self._assign_sanatorium(payload.sanatorium_id, user.id)
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
        sanatorium_id = data.pop("sanatorium_id", _MISSING)
        for field, value in data.items():
            setattr(user, field, value)
        if sanatorium_id is not _MISSING:
            target_role = data.get("role", user.role)
            if sanatorium_id is None:
                await self._unassign_sanatoriums(user.id)
            else:
                self._assert_role_can_own_sanatorium(target_role)
                await self._assign_sanatorium(sanatorium_id, user.id)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def primary_sanatorium_id(self, user_id: uuid.UUID) -> uuid.UUID | None:
        return (
            await self.db.execute(
                select(Sanatorium.id)
                .where(Sanatorium.admin_user_id == user_id)
                .order_by(Sanatorium.created_at.asc())
                .limit(1)
            )
        ).scalar_one_or_none()

    async def to_read(self, user: User) -> UserRead:
        sanatorium_id: uuid.UUID | None = None
        if user.role == UserRole.ADMIN:
            sanatorium_id = await self.primary_sanatorium_id(user.id)
        return UserRead.model_validate(
            {
                "id": user.id,
                "email": user.email,
                "role": user.role,
                "full_name": user.full_name,
                "phone": user.phone,
                "is_active": user.is_active,
                "sanatorium_id": sanatorium_id,
                "created_at": user.created_at,
            }
        )

    async def to_read_bulk(self, users: Sequence[User]) -> list[UserRead]:
        admin_ids = [u.id for u in users if u.role == UserRole.ADMIN]
        mapping: dict[uuid.UUID, uuid.UUID] = {}
        if admin_ids:
            rows = (
                await self.db.execute(
                    select(Sanatorium.admin_user_id, Sanatorium.id)
                    .where(Sanatorium.admin_user_id.in_(admin_ids))
                    .order_by(Sanatorium.created_at.asc())
                )
            ).all()
            for admin_user_id, sanatorium_id in rows:
                mapping.setdefault(admin_user_id, sanatorium_id)
        return [
            UserRead.model_validate(
                {
                    "id": u.id,
                    "email": u.email,
                    "role": u.role,
                    "full_name": u.full_name,
                    "phone": u.phone,
                    "is_active": u.is_active,
                    "sanatorium_id": mapping.get(u.id),
                    "created_at": u.created_at,
                }
            )
            for u in users
        ]

    @staticmethod
    def _assert_role_can_own_sanatorium(role: UserRole) -> None:
        if role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only admin role can be assigned to a sanatorium",
            )

    async def _assign_sanatorium(
        self, sanatorium_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        sanatorium = await self.db.get(Sanatorium, sanatorium_id)
        if sanatorium is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Sanatorium not found",
            )
        sanatorium.admin_user_id = user_id

    async def _unassign_sanatoriums(self, user_id: uuid.UUID) -> None:
        rows = (
            (
                await self.db.execute(
                    select(Sanatorium).where(Sanatorium.admin_user_id == user_id)
                )
            )
            .scalars()
            .all()
        )
        for s in rows:
            s.admin_user_id = None


_MISSING: object = object()


def get_user_service(db: AsyncSession = Depends(get_db)) -> UserService:
    return UserService(db)
