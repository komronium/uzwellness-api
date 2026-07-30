import uuid

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import not_found, require_roles
from app.core.pagination import LargePagination
from app.models.transfer_request import VehicleType
from app.models.user import UserRole
from app.schemas.transfer_vehicle import (
    TransferVehicleCreate,
    TransferVehicleList,
    TransferVehicleRead,
    TransferVehicleUpdate,
)
from app.services.transfer_vehicle_service import (
    TransferVehicleService,
    get_transfer_vehicle_service,
)

router = APIRouter(
    prefix="/transfer-vehicles",
    tags=["Travel Services"],
    dependencies=[
        Depends(require_roles(UserRole.TRANSFER_ADMIN, UserRole.SUPER_ADMIN))
    ],
)


@router.get("", response_model=TransferVehicleList)
async def list_transfer_vehicles(
    page: LargePagination,
    is_active: bool | None = Query(default=None),
    vehicle_type: VehicleType | None = Query(default=None),
    vehicles: TransferVehicleService = Depends(get_transfer_vehicle_service),
) -> TransferVehicleList:
    items, total = await vehicles.list_all(
        limit=page.limit,
        offset=page.offset,
        is_active=is_active,
        vehicle_type=vehicle_type,
    )
    return TransferVehicleList(
        items=[TransferVehicleRead.model_validate(v) for v in items],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.post(
    "", response_model=TransferVehicleRead, status_code=status.HTTP_201_CREATED
)
async def create_transfer_vehicle(
    payload: TransferVehicleCreate,
    vehicles: TransferVehicleService = Depends(get_transfer_vehicle_service),
) -> TransferVehicleRead:
    return TransferVehicleRead.model_validate(await vehicles.create(payload))


@router.patch("/{vehicle_id}", response_model=TransferVehicleRead)
async def update_transfer_vehicle(
    vehicle_id: uuid.UUID,
    payload: TransferVehicleUpdate,
    vehicles: TransferVehicleService = Depends(get_transfer_vehicle_service),
) -> TransferVehicleRead:
    vehicle = await vehicles.get_by_id(vehicle_id)
    if vehicle is None:
        raise not_found("Transfer vehicle not found")
    return TransferVehicleRead.model_validate(await vehicles.update(vehicle, payload))


@router.delete("/{vehicle_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transfer_vehicle(
    vehicle_id: uuid.UUID,
    vehicles: TransferVehicleService = Depends(get_transfer_vehicle_service),
) -> None:
    vehicle = await vehicles.get_by_id(vehicle_id)
    if vehicle is None:
        raise not_found("Transfer vehicle not found")
    await vehicles.delete(vehicle)
