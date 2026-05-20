import uuid
from collections.abc import Sequence

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.pagination import paginated
from app.core.permissions import assert_sanatorium_access
from app.core.utils import merge_translation_fields
from app.models.extra_bed import ExtraBedConfig
from app.models.user import User
from app.schemas.extra_bed import ExtraBedConfigCreate, ExtraBedConfigUpdate

_ACTION = "manage this sanatorium's extra beds"


class ExtraBedService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_for_sanatorium(
        self,
        sanatorium_id: uuid.UUID,
        *,
        limit: int,
        offset: int,
        active_only: bool = False,
    ) -> tuple[Sequence[ExtraBedConfig], int]:
        stmt = (
            select(ExtraBedConfig)
            .where(ExtraBedConfig.sanatorium_id == sanatorium_id)
            .order_by(ExtraBedConfig.created_at.asc())
        )
        if active_only:
            stmt = stmt.where(ExtraBedConfig.is_active.is_(True))
        return await paginated(self.db, stmt, limit=limit, offset=offset)

    async def get_by_id(self, config_id: uuid.UUID) -> ExtraBedConfig | None:
        stmt = select(ExtraBedConfig).where(ExtraBedConfig.id == config_id)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def create(
        self, payload: ExtraBedConfigCreate, user: User
    ) -> ExtraBedConfig:
        await assert_sanatorium_access(
            self.db, payload.sanatorium_id, user, action=_ACTION
        )
        config = ExtraBedConfig(
            sanatorium_id=payload.sanatorium_id,
            name=payload.name.model_dump(exclude_none=True),
            description=payload.description.model_dump(exclude_none=True),
            price_per_night=payload.price_per_night,
            currency=payload.currency,
            max_count=payload.max_count,
        )
        self.db.add(config)
        await self.db.commit()
        await self.db.refresh(config)
        return config

    async def update(
        self,
        config: ExtraBedConfig,
        payload: ExtraBedConfigUpdate,
        user: User,
    ) -> ExtraBedConfig:
        await assert_sanatorium_access(
            self.db, config.sanatorium_id, user, action=_ACTION
        )
        data = payload.model_dump(exclude_unset=True)
        merge_translation_fields(config, data, ("name", "description"))
        for field, value in data.items():
            setattr(config, field, value)
        await self.db.commit()
        await self.db.refresh(config)
        return config

    async def delete(self, config: ExtraBedConfig, user: User) -> None:
        await assert_sanatorium_access(
            self.db, config.sanatorium_id, user, action=_ACTION
        )
        await self.db.delete(config)
        await self.db.commit()


def get_extra_bed_service(db: AsyncSession = Depends(get_db)) -> ExtraBedService:
    return ExtraBedService(db)
