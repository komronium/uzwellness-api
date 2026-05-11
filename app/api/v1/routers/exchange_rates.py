from fastapi import APIRouter, Depends

from app.api.deps import require_roles
from app.models.user import UserRole
from app.schemas.exchange_rate import ExchangeRateRead, ExchangeRateUpsert
from app.services.room_service import RoomService, get_room_service

router = APIRouter(prefix="/exchange-rates", tags=["exchange-rates"])

require_super_admin = require_roles(UserRole.SUPER_ADMIN)


@router.get("", response_model=list[ExchangeRateRead])
async def list_exchange_rates(
    rooms: RoomService = Depends(get_room_service),
) -> list[ExchangeRateRead]:
    rates = await rooms.list_exchange_rates()
    return [ExchangeRateRead.model_validate(r) for r in rates]


@router.patch(
    "",
    response_model=ExchangeRateRead,
    dependencies=[Depends(require_super_admin)],
)
async def upsert_exchange_rate(
    payload: ExchangeRateUpsert,
    rooms: RoomService = Depends(get_room_service),
) -> ExchangeRateRead:
    rate = await rooms.upsert_exchange_rate(payload)
    return ExchangeRateRead.model_validate(rate)
