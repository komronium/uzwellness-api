from fastapi import APIRouter, Depends

from app.api.deps import require_roles
from app.models.user import UserRole
from app.schemas.admin import AdminStats
from app.schemas.app_config import AdminConfig, HomepageConfig
from app.services.admin_service import AdminService, get_admin_service
from app.services.app_config_service import (
    AppConfigService,
    get_app_config_service,
)

router = APIRouter(prefix="/admin", tags=["Admin"])

require_admin_or_above = require_roles(UserRole.ADMIN, UserRole.SUPER_ADMIN)
require_super_admin = require_roles(UserRole.SUPER_ADMIN)


@router.get(
    "/stats",
    response_model=AdminStats,
    dependencies=[Depends(require_admin_or_above)],
)
async def get_stats(
    admin: AdminService = Depends(get_admin_service),
) -> AdminStats:
    data = await admin.get_stats()
    return AdminStats(**data)


@router.get(
    "/config",
    response_model=AdminConfig,
    dependencies=[Depends(require_super_admin)],
)
async def get_admin_config(
    configs: AppConfigService = Depends(get_app_config_service),
) -> AdminConfig:
    return await configs.get_admin_config()


@router.put(
    "/config",
    response_model=AdminConfig,
    dependencies=[Depends(require_super_admin)],
)
async def put_admin_config(
    payload: AdminConfig,
    configs: AppConfigService = Depends(get_app_config_service),
) -> AdminConfig:
    return await configs.put_admin_config(payload)


@router.get("/homepage-config", response_model=HomepageConfig)
async def get_homepage_config(
    configs: AppConfigService = Depends(get_app_config_service),
) -> HomepageConfig:
    return await configs.get_homepage_config()


@router.put(
    "/homepage-config",
    response_model=HomepageConfig,
    dependencies=[Depends(require_super_admin)],
)
async def put_homepage_config(
    payload: HomepageConfig,
    configs: AppConfigService = Depends(get_app_config_service),
) -> HomepageConfig:
    return await configs.put_homepage_config(payload)
