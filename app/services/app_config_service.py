from typing import TypeVar

from fastapi import Depends
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.app_config import AppConfig
from app.schemas.app_config import AdminConfig, HomepageConfig

ADMIN_CONFIG_KEY = "admin_config"
HOMEPAGE_CONFIG_KEY = "homepage_config"

T = TypeVar("T", bound=BaseModel)


class AppConfigService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_admin_config(self) -> AdminConfig:
        return await self._get(ADMIN_CONFIG_KEY, AdminConfig)

    async def put_admin_config(self, payload: AdminConfig) -> AdminConfig:
        return await self._put(ADMIN_CONFIG_KEY, payload)

    async def get_homepage_config(self) -> HomepageConfig:
        return await self._get(HOMEPAGE_CONFIG_KEY, HomepageConfig)

    async def put_homepage_config(self, payload: HomepageConfig) -> HomepageConfig:
        return await self._put(HOMEPAGE_CONFIG_KEY, payload)

    async def _get(self, key: str, schema: type[T]) -> T:
        row = await self.db.get(AppConfig, key)
        if row is None:
            return schema()
        try:
            return schema.model_validate(row.value)
        except ValidationError:
            # Stored value predates a schema change; fall back to defaults.
            return schema()

    async def _put(self, key: str, payload: T) -> T:
        row = await self.db.get(AppConfig, key)
        value = payload.model_dump(mode="json")
        if row is None:
            self.db.add(AppConfig(key=key, value=value))
        else:
            row.value = value
        await self.db.commit()
        return payload


def get_app_config_service(db: AsyncSession = Depends(get_db)) -> AppConfigService:
    return AppConfigService(db)
