from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import CurrentUser
from app.models.user import UserRole
from app.schemas.b2b import B2BClient, B2BClientList, B2BDashboard
from app.services.b2b_service import B2BService, get_b2b_service

router = APIRouter(prefix="/b2b", tags=["b2b"])


def _require_b2b(user) -> None:
    if user.role != UserRole.AGENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="B2B account required",
        )


@router.get("/dashboard", response_model=B2BDashboard)
async def get_dashboard(
    current_user: CurrentUser,
    b2b: B2BService = Depends(get_b2b_service),
) -> B2BDashboard:
    _require_b2b(current_user)
    data = await b2b.dashboard(current_user)
    return B2BDashboard(**data)


@router.get("/clients", response_model=B2BClientList)
async def list_clients(
    current_user: CurrentUser,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    b2b: B2BService = Depends(get_b2b_service),
) -> B2BClientList:
    _require_b2b(current_user)
    items, total = await b2b.clients(current_user, limit=limit, offset=offset)
    return B2BClientList(
        items=[B2BClient(**{**c, "booking_id": str(c["booking_id"])}) for c in items],
        total=total,
        limit=limit,
        offset=offset,
    )
