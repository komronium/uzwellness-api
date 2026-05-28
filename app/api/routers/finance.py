import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query

from app.api.deps import CurrentUser
from app.core.pagination import Pagination
from app.schemas.finance import FinanceOrderItem, FinanceOrdersList, FinanceSummary
from app.services.finance_service import FinanceService, get_finance_service

router = APIRouter(prefix="/finance", tags=["Finance"])


@router.get("/summary", response_model=FinanceSummary)
async def get_finance_summary(
    current_user: CurrentUser,
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    sanatorium_id: uuid.UUID | None = Query(default=None),
    agent_id: uuid.UUID | None = Query(default=None),
    is_b2b: bool | None = Query(default=None),
    finance: FinanceService = Depends(get_finance_service),
) -> FinanceSummary:
    data = await finance.summary(
        current_user,
        date_from=date_from,
        date_to=date_to,
        sanatorium_id=sanatorium_id,
        agent_id=agent_id,
        is_b2b=is_b2b,
    )
    return FinanceSummary(**data)


@router.get("/orders", response_model=FinanceOrdersList)
async def list_finance_orders(
    current_user: CurrentUser,
    page: Pagination,
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    sanatorium_id: uuid.UUID | None = Query(default=None),
    agent_id: uuid.UUID | None = Query(default=None),
    is_b2b: bool | None = Query(default=None),
    finance: FinanceService = Depends(get_finance_service),
) -> FinanceOrdersList:
    items, total = await finance.orders(
        current_user,
        limit=page.limit,
        offset=page.offset,
        date_from=date_from,
        date_to=date_to,
        sanatorium_id=sanatorium_id,
        agent_id=agent_id,
        is_b2b=is_b2b,
    )
    return FinanceOrdersList(
        items=[FinanceOrderItem(**item) for item in items],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )
