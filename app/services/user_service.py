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
        return await self.db.scalar(select(User).where(User.email == email.lower()))

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
        if payload.role == UserRole.TRANSFER_ADMIN:
            await self._assert_no_other_transfer_admin()
        user = User(
            email=payload.email.lower(),
            password_hash=hash_password(payload.password),
            role=payload.role,
            full_name=payload.full_name,
            phone=payload.phone,
            transfer_commission_percent=(
                payload.transfer_commission_percent
                if payload.role == UserRole.TRANSFER_ADMIN
                else None
            ),
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

        total = await self.db.scalar(select(func.count()).select_from(base.subquery()))
        stmt = base.order_by(User.created_at.desc()).limit(limit).offset(offset)
        rows = (await self.db.scalars(stmt)).all()
        return rows, total or 0

    async def update(self, user: User, payload: UserUpdate) -> User:
        data = payload.model_dump(exclude_unset=True)
        email = data.pop("email", None)
        if email is not None:
            email = email.lower()
            existing = await self.get_by_email(email)
            if existing is not None and existing.id != user.id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Email already registered",
                )
            data["email"] = email
        sanatorium_id = data.pop("sanatorium_id", _MISSING)
        await self._apply_transfer_admin_rules(user, data)
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
        return await self.db.scalar(
            select(Sanatorium.id)
            .where(Sanatorium.admin_user_id == user_id)
            .order_by(Sanatorium.created_at.asc())
            .limit(1)
        )

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
                "transfer_commission_percent": user.transfer_commission_percent,
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
                    "transfer_commission_percent": u.transfer_commission_percent,
                    "created_at": u.created_at,
                }
            )
            for u in users
        ]

    async def _apply_transfer_admin_rules(self, user: User, data: dict) -> None:
        """Keep the single-operator invariant and the commission in sync.

        Mutates ``data`` so the caller's plain setattr loop stays valid: the
        commission is cleared when the user leaves the transfer_admin role.
        """
        target_role = data.get("role", user.role)
        commission = data.get("transfer_commission_percent", _MISSING)

        if target_role != UserRole.TRANSFER_ADMIN:
            if user.role == UserRole.TRANSFER_ADMIN:
                data["transfer_commission_percent"] = None
            elif commission is not _MISSING and commission is not None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "transfer_commission_percent only applies to the "
                        "transfer_admin role"
                    ),
                )
            return

        if user.role != UserRole.TRANSFER_ADMIN:
            await self._assert_no_other_transfer_admin(exclude_id=user.id)

        effective = (
            commission
            if commission is not _MISSING
            else user.transfer_commission_percent
        )
        if effective is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    "transfer_commission_percent is required for the "
                    "transfer_admin role"
                ),
            )

    async def _assert_no_other_transfer_admin(
        self, *, exclude_id: uuid.UUID | None = None
    ) -> None:
        stmt = select(User.id).where(User.role == UserRole.TRANSFER_ADMIN)
        if exclude_id is not None:
            stmt = stmt.where(User.id != exclude_id)
        existing_id = await self.db.scalar(stmt.limit(1))
        if existing_id is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "transfer_admin_exists",
                    "existing_user_id": str(existing_id),
                },
            )

    async def transfer_admin(self) -> User | None:
        return await self.db.scalar(
            select(User).where(User.role == UserRole.TRANSFER_ADMIN).limit(1)
        )

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
            await self.db.scalars(
                select(Sanatorium).where(Sanatorium.admin_user_id == user_id)
            )
        ).all()
        for s in rows:
            s.admin_user_id = None


_MISSING: object = object()


def get_user_service(db: AsyncSession = Depends(get_db)) -> UserService:
    return UserService(db)
