import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import CurrentUser
from app.core.pagination import Pagination
from app.models.user import UserRole
from app.schemas.b2b import (
    B2BDashboard,
    B2BDiscountStatus,
    B2BOrderItem,
    B2BOrdersList,
)
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


@router.get("/discount-status", response_model=B2BDiscountStatus)
async def get_discount_status(
    current_user: CurrentUser,
    sanatorium_id: uuid.UUID = Query(...),
    b2b: B2BService = Depends(get_b2b_service),
) -> B2BDiscountStatus:
    _require_b2b(current_user)
    data = await b2b.discount_status(current_user, sanatorium_id)
    return B2BDiscountStatus(**data)


@router.get("/orders", response_model=B2BOrdersList)
async def list_orders(
    current_user: CurrentUser,
    page: Pagination,
    b2b: B2BService = Depends(get_b2b_service),
) -> B2BOrdersList:
    _require_b2b(current_user)
    items, total = await b2b.orders(
        current_user, limit=page.limit, offset=page.offset
    )
    return B2BOrdersList(
        items=[B2BOrderItem(**item) for item in items],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )
