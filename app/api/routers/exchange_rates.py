from fastapi import APIRouter, Depends

from app.api.deps import require_roles
from app.models.user import UserRole
from app.schemas.exchange_rate import ExchangeRateRead, ExchangeRateUpsert
from app.services.exchange_rate_service import (
    ExchangeRateService,
    get_exchange_rate_service,
)

router = APIRouter(prefix="/exchange-rates", tags=["Payments"])

require_super_admin = require_roles(UserRole.SUPER_ADMIN)


@router.get("", response_model=list[ExchangeRateRead])
async def list_exchange_rates(
    rates: ExchangeRateService = Depends(get_exchange_rate_service),
) -> list[ExchangeRateRead]:
    items = await rates.list_all()
    return [ExchangeRateRead.model_validate(r) for r in items]


@router.patch(
    "",
    response_model=ExchangeRateRead,
    dependencies=[Depends(require_super_admin)],
)
async def upsert_exchange_rate(
    payload: ExchangeRateUpsert,
    rates: ExchangeRateService = Depends(get_exchange_rate_service),
) -> ExchangeRateRead:
    return ExchangeRateRead.model_validate(await rates.upsert(payload))
