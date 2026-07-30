import uuid

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import ConverterDep, CurrentUser, not_found, require_roles
from app.core.currency import CurrencyConverter
from app.core.pagination import LargePagination
from app.models.transfer_request import VehicleType
from app.models.transfer_tariff import TransferTariff
from app.models.user import UserRole
from app.schemas.transfer_tariff import (
    TransferTariffCreate,
    TransferTariffList,
    TransferTariffRead,
)
from app.services.transfer_tariff_service import (
    TransferTariffService,
    get_transfer_tariff_service,
)

router = APIRouter(prefix="/transfer-tariffs", tags=["Travel Services"])

require_transfer_admin = require_roles(UserRole.TRANSFER_ADMIN, UserRole.SUPER_ADMIN)


def _to_read(
    tariff: TransferTariff, converter: CurrencyConverter
) -> TransferTariffRead:
    data = TransferTariffRead.model_validate(tariff)
    data.display_price = converter.convert(tariff.price, tariff.currency)
    data.display_currency = converter.target
    return data


@router.get("", response_model=TransferTariffList)
async def list_transfer_tariffs(
    current_user: CurrentUser,
    converter: ConverterDep,
    page: LargePagination,
    route_from_id: uuid.UUID | None = Query(default=None),
    route_to_id: uuid.UUID | None = Query(default=None),
    vehicle_type: VehicleType | None = Query(default=None),
    current_only: bool = Query(default=False),
    tariffs: TransferTariffService = Depends(get_transfer_tariff_service),
) -> TransferTariffList:
    """Price history, newest version first. Filter to the live prices with
    `current_only=true`."""
    items, total = await tariffs.list_versions(
        limit=page.limit,
        offset=page.offset,
        route_from_id=route_from_id,
        route_to_id=route_to_id,
        vehicle_type=vehicle_type,
        current_only=current_only,
    )
    return TransferTariffList(
        items=[_to_read(t, converter) for t in items],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/current", response_model=TransferTariffRead)
async def get_current_transfer_tariff(
    converter: ConverterDep,
    route_from_id: uuid.UUID = Query(),
    route_to_id: uuid.UUID = Query(),
    vehicle_type: VehicleType = Query(),
    tariffs: TransferTariffService = Depends(get_transfer_tariff_service),
) -> TransferTariffRead:
    """Live price for one leg — the checkout add-on block renders on a 200 here."""
    tariff = await tariffs.current(
        route_from_id=route_from_id,
        route_to_id=route_to_id,
        vehicle_type=vehicle_type,
    )
    if tariff is None:
        raise not_found("No current tariff for this route and vehicle type")
    return _to_read(tariff, converter)


@router.post(
    "",
    response_model=TransferTariffRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_transfer_admin)],
)
async def create_transfer_tariff(
    payload: TransferTariffCreate,
    converter: ConverterDep,
    tariffs: TransferTariffService = Depends(get_transfer_tariff_service),
) -> TransferTariffRead:
    """Publish a new price. The previous version is closed, never overwritten."""
    return _to_read(await tariffs.create(payload), converter)
