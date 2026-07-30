import uuid

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import ConverterDep, CurrentUser, LocaleDep, not_found
from app.core.currency import CurrencyConverter
from app.core.pagination import Pagination
from app.models.transfer_request import (
    TransferPaymentState,
    TransferRequest,
    TransferStatus,
)
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


def _to_read(
    transfer: TransferRequest, converter: CurrencyConverter
) -> TransferRequestRead:
    data = TransferRequestRead.model_validate(transfer)
    amount = (
        transfer.applied_price if transfer.applied_price is not None else transfer.price
    )
    currency = transfer.applied_currency or transfer.currency
    if amount is not None and currency:
        data.display_price = converter.convert(amount, currency)
        data.display_currency = converter.target
    return data


@router.get("", response_model=TransferRequestList)
async def list_transfers(
    current_user: CurrentUser,
    converter: ConverterDep,
    page: Pagination,
    status_filter: TransferStatus | None = Query(default=None, alias="status"),
    payment_state: TransferPaymentState | None = Query(default=None),
    booking_id: uuid.UUID | None = Query(default=None),
    transfers: TransferRequestService = Depends(get_transfer_request_service),
) -> TransferRequestList:
    """Transfer operators see every order; everyone else sees their own."""
    items, total = await transfers.list_for_user(
        current_user,
        limit=page.limit,
        offset=page.offset,
        status_filter=status_filter,
        payment_state=payment_state,
        booking_id=booking_id,
    )
    return TransferRequestList(
        items=[_to_read(t, converter) for t in items],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/{transfer_id}", response_model=TransferRequestRead)
async def get_transfer(
    transfer_id: uuid.UUID,
    current_user: CurrentUser,
    converter: ConverterDep,
    transfers: TransferRequestService = Depends(get_transfer_request_service),
) -> TransferRequestRead:
    transfer = await transfers.get_visible(transfer_id, current_user)
    if transfer is None:
        raise not_found("Transfer request not found")
    return _to_read(transfer, converter)


@router.post(
    "",
    response_model=TransferRequestRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_transfer(
    payload: TransferRequestCreate,
    current_user: CurrentUser,
    converter: ConverterDep,
    locale: LocaleDep,
    transfers: TransferRequestService = Depends(get_transfer_request_service),
) -> TransferRequestRead:
    """Order a transfer outside checkout. Priced at the current tariff when
    `route_from_id`/`route_to_id` are given, and always settled separately
    (`payment_state='unpaid'`)."""
    transfer = await transfers.create(payload, current_user, locale=locale)
    return _to_read(transfer, converter)


@router.patch("/{transfer_id}", response_model=TransferRequestRead)
async def update_transfer(
    transfer_id: uuid.UUID,
    payload: TransferRequestUpdate,
    current_user: CurrentUser,
    converter: ConverterDep,
    transfers: TransferRequestService = Depends(get_transfer_request_service),
) -> TransferRequestRead:
    """Role-split edit: operators set status, vehicle, driver and price; the
    guest may only correct their own flight and contact details."""
    transfer = await transfers.get_visible(transfer_id, current_user)
    if transfer is None:
        raise not_found("Transfer request not found")
    updated = await transfers.apply_patch(transfer, payload, current_user)
    return _to_read(updated, converter)


@router.post("/{transfer_id}/cancel", response_model=TransferRequestRead)
@router.patch(
    "/{transfer_id}/cancel",
    response_model=TransferRequestRead,
    deprecated=True,
)
async def cancel_transfer(
    transfer_id: uuid.UUID,
    current_user: CurrentUser,
    converter: ConverterDep,
    transfers: TransferRequestService = Depends(get_transfer_request_service),
) -> TransferRequestRead:
    transfer = await transfers.get_visible(transfer_id, current_user)
    if transfer is None:
        raise not_found("Transfer request not found")
    return _to_read(await transfers.cancel(transfer, current_user), converter)
