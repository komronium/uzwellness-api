import uuid

from fastapi import APIRouter, Depends, Query

from app.api.deps import CurrentUser, require_roles
from app.core.pagination import Pagination
from app.models.user import UserRole
from app.schemas.b2b import (
    B2BDashboard,
    B2BDiscountStatus,
    B2BOrderItem,
    B2BOrdersList,
)
from app.services.b2b_service import B2BService, get_b2b_service

require_b2b = require_roles(UserRole.AGENT, detail="B2B account required")

router = APIRouter(prefix="/b2b", tags=["B2B"], dependencies=[Depends(require_b2b)])


@router.get("/dashboard", response_model=B2BDashboard)
async def get_dashboard(
    current_user: CurrentUser,
    b2b: B2BService = Depends(get_b2b_service),
) -> B2BDashboard:
    data = await b2b.dashboard(current_user)
    return B2BDashboard(**data)


@router.get("/discount-status", response_model=B2BDiscountStatus)
async def get_discount_status(
    current_user: CurrentUser,
    sanatorium_id: uuid.UUID = Query(...),
    b2b: B2BService = Depends(get_b2b_service),
) -> B2BDiscountStatus:
    data = await b2b.discount_status(current_user, sanatorium_id)
    return B2BDiscountStatus(**data)


@router.get("/orders", response_model=B2BOrdersList)
async def list_orders(
    current_user: CurrentUser,
    page: Pagination,
    b2b: B2BService = Depends(get_b2b_service),
) -> B2BOrdersList:
    items, total = await b2b.orders(current_user, limit=page.limit, offset=page.offset)
    return B2BOrdersList(
        items=[B2BOrderItem(**item) for item in items],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )
