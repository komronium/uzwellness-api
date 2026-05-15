from fastapi import APIRouter, Depends

from app.api.deps import require_roles
from app.models.user import UserRole
from app.schemas.admin import AdminStats
from app.services.admin_service import AdminService, get_admin_service

router = APIRouter(prefix="/admin", tags=["admin"])

require_admin_or_above = require_roles(UserRole.ADMIN, UserRole.SUPER_ADMIN)


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
