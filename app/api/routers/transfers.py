import uuid

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, not_found, require_roles
from app.core.pagination import Pagination
from app.models.transfer_request import TransferStatus
from app.models.user import UserRole
from app.schemas.transfer_request import (
    TransferRequestCreate,
    TransferRequestList,
    TransferRequestRead,
    TransferRequestUpdate,
)
from app.services.transfer_request_service import (
    TransferRequestService,
    get_transfer_request_service,
)

router = APIRouter(prefix="/transfers", tags=["Travel Services"])

require_super_admin = require_roles(UserRole.SUPER_ADMIN)


@router.get("", response_model=TransferRequestList)
async def list_transfers(
    current_user: CurrentUser,
    page: Pagination,
    status_filter: TransferStatus | None = Query(default=None, alias="status"),
    transfers: TransferRequestService = Depends(get_transfer_request_service),
) -> TransferRequestList:
    items, total = await transfers.list_for_user(
        current_user,
        limit=page.limit,
        offset=page.offset,
        status_filter=status_filter,
    )
    return TransferRequestList(
        items=[TransferRequestRead.model_validate(t) for t in items],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/{transfer_id}", response_model=TransferRequestRead)
async def get_transfer(
    transfer_id: uuid.UUID,
    current_user: CurrentUser,
    transfers: TransferRequestService = Depends(get_transfer_request_service),
) -> TransferRequestRead:
    transfer = await transfers.get_visible(transfer_id, current_user)
    if transfer is None:
        raise not_found("Transfer request not found")
    return TransferRequestRead.model_validate(transfer)


@router.post(
    "",
    response_model=TransferRequestRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_transfer(
    payload: TransferRequestCreate,
    current_user: CurrentUser,
    transfers: TransferRequestService = Depends(get_transfer_request_service),
) -> TransferRequestRead:
    return TransferRequestRead.model_validate(
        await transfers.create(payload, current_user)
    )


@router.patch(
    "/{transfer_id}",
    response_model=TransferRequestRead,
    dependencies=[Depends(require_super_admin)],
)
async def update_transfer(
    transfer_id: uuid.UUID,
    payload: TransferRequestUpdate,
    transfers: TransferRequestService = Depends(get_transfer_request_service),
) -> TransferRequestRead:
    transfer = await transfers.get_by_id(transfer_id)
    if transfer is None:
        raise not_found("Transfer request not found")
    return TransferRequestRead.model_validate(
        await transfers.update(transfer, payload)
    )


@router.patch("/{transfer_id}/cancel", response_model=TransferRequestRead)
async def cancel_transfer(
    transfer_id: uuid.UUID,
    current_user: CurrentUser,
    transfers: TransferRequestService = Depends(get_transfer_request_service),
) -> TransferRequestRead:
    transfer = await transfers.get_visible(transfer_id, current_user)
    if transfer is None:
        raise not_found("Transfer request not found")
    return TransferRequestRead.model_validate(
        await transfers.cancel(transfer, current_user)
    )
