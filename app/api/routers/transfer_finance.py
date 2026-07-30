from datetime import date

from fastapi import APIRouter, Depends, Query

from app.api.deps import require_roles
from app.core.pagination import Pagination
from app.models.user import UserRole
from app.schemas.transfer_finance import (
    TransferFinanceOrderItem,
    TransferFinanceOrdersList,
    TransferFinanceSummary,
)
from app.services.transfer_finance_service import (
    TransferFinanceService,
    get_transfer_finance_service,
)

router = APIRouter(
    prefix="/transfer-finance",
    tags=["Finance"],
    dependencies=[
        Depends(require_roles(UserRole.TRANSFER_ADMIN, UserRole.SUPER_ADMIN))
    ],
)


@router.get("/summary", response_model=TransferFinanceSummary)
async def transfer_finance_summary(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    currency: str | None = Query(default=None, max_length=3),
    finance: TransferFinanceService = Depends(get_transfer_finance_service),
) -> TransferFinanceSummary:
    """Per-currency settlement totals. Cancelled transfers are excluded."""
    return TransferFinanceSummary.model_validate(
        await finance.summary(date_from=date_from, date_to=date_to, currency=currency)
    )


@router.get("/orders", response_model=TransferFinanceOrdersList)
async def transfer_finance_orders(
    page: Pagination,
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    currency: str | None = Query(default=None, max_length=3),
    finance: TransferFinanceService = Depends(get_transfer_finance_service),
) -> TransferFinanceOrdersList:
    items, total = await finance.orders(
        limit=page.limit,
        offset=page.offset,
        date_from=date_from,
        date_to=date_to,
        currency=currency,
    )
    return TransferFinanceOrdersList(
        items=[TransferFinanceOrderItem.model_validate(i) for i in items],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )
