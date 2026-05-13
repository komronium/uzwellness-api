import uuid
from collections.abc import Sequence

from fastapi import Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.extra_bed import ExtraBedConfig
from app.models.sanatorium import Sanatorium
from app.models.user import User, UserRole
from app.schemas.extra_bed import ExtraBedConfigCreate, ExtraBedConfigUpdate


class ExtraBedService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_for_sanatorium(
        self, sanatorium_id: uuid.UUID, *, limit: int, offset: int, active_only: bool = False
    ) -> tuple[Sequence[ExtraBedConfig], int]:
        base = select(ExtraBedConfig).where(ExtraBedConfig.sanatorium_id == sanatorium_id)
        if active_only:
            base = base.where(ExtraBedConfig.is_active.is_(True))
        total = (await self.db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
        rows = (await self.db.execute(
            base.order_by(ExtraBedConfig.created_at.asc()).limit(limit).offset(offset)
        )).scalars().all()
        return rows, total

    async def get_by_id(self, config_id: uuid.UUID) -> ExtraBedConfig | None:
        return (await self.db.execute(
            select(ExtraBedConfig).where(ExtraBedConfig.id == config_id)
        )).scalar_one_or_none()

    async def create(self, payload: ExtraBedConfigCreate, user: User) -> ExtraBedConfig:
        sanatorium = await self._check_sanatorium_access(payload.sanatorium_id, user)
        if sanatorium is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sanatorium not found or not accessible")

        config = ExtraBedConfig(
            sanatorium_id=payload.sanatorium_id,
            name=payload.name.model_dump(exclude_none=True),
            price_per_night=payload.price_per_night,
            currency=payload.currency,
            max_count=payload.max_count,
        )
        self.db.add(config)
        await self.db.commit()
        await self.db.refresh(config)
        return config

    async def update(self, config: ExtraBedConfig, payload: ExtraBedConfigUpdate, user: User) -> ExtraBedConfig:
        await self._check_sanatorium_access(config.sanatorium_id, user)
        data = payload.model_dump(exclude_unset=True)
        if "name" in data and data["name"] is not None:
            data["name"] = {k: v for k, v in data["name"].items() if v is not None}
        for field, value in data.items():
            setattr(config, field, value)
        await self.db.commit()
        await self.db.refresh(config)
        return config

    async def delete(self, config: ExtraBedConfig, user: User) -> None:
        await self._check_sanatorium_access(config.sanatorium_id, user)
        await self.db.delete(config)
        await self.db.commit()

    async def _check_sanatorium_access(self, sanatorium_id: uuid.UUID, user: User) -> Sanatorium | None:
        sanatorium = (await self.db.execute(
            select(Sanatorium).where(Sanatorium.id == sanatorium_id)
        )).scalar_one_or_none()
        if sanatorium is None:
            return None
        if user.role == UserRole.SUPER_ADMIN:
            return sanatorium
        if user.role == UserRole.ADMIN and sanatorium.admin_user_id == user.id:
            return sanatorium
        return None


def get_extra_bed_service(db: AsyncSession = Depends(get_db)) -> ExtraBedService:
    return ExtraBedService(db)
