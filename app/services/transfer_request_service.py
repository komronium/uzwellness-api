import logging
import uuid
from collections.abc import Sequence

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.booking_attachment import resolve_owner_for_booking
from app.core.database import get_db
from app.core.pagination import paginated
from app.models.transfer_request import (
    TransferPaymentState,
    TransferRequest,
    TransferStatus,
)
from app.models.transfer_vehicle import TransferVehicle
from app.models.user import User, UserRole
from app.schemas.transfer_request import (
    CUSTOMER_EDITABLE_FIELDS,
    TransferRequestCreate,
    TransferRequestUpdate,
)
from app.services.email_service import (
    send_transfer_confirmed,
    send_transfer_driver_assigned,
)
from app.services.transfer_pricing import price_transfer
from app.services.transfer_tariff_service import (
    TransferTariffService,
    get_transfer_tariff_service,
)

logger = logging.getLogger("uzwellness.transfers")

_CANCELLABLE_STATUSES = {TransferStatus.REQUESTED, TransferStatus.CONFIRMED}
_OPERATOR_ROLES = {UserRole.TRANSFER_ADMIN, UserRole.SUPER_ADMIN}


def is_transfer_operator(user: User) -> bool:
    return user.role in _OPERATOR_ROLES


class TransferRequestService:
    def __init__(self, db: AsyncSession, tariffs: TransferTariffService) -> None:
        self.db = db
        self.tariffs = tariffs

    async def get_by_id(self, transfer_id: uuid.UUID) -> TransferRequest | None:
        return await self.db.get(TransferRequest, transfer_id)

    async def get_visible(
        self, transfer_id: uuid.UUID, user: User
    ) -> TransferRequest | None:
        transfer = await self.get_by_id(transfer_id)
        if transfer is None:
            return None
        if is_transfer_operator(user) or transfer.user_id == user.id:
            return transfer
        return None

    async def list_for_user(
        self,
        user: User,
        *,
        limit: int,
        offset: int,
        status_filter: TransferStatus | None = None,
        payment_state: TransferPaymentState | None = None,
        booking_id: uuid.UUID | None = None,
    ) -> tuple[Sequence[TransferRequest], int]:
        stmt = select(TransferRequest).order_by(TransferRequest.created_at.desc())
        if not is_transfer_operator(user):
            stmt = stmt.where(TransferRequest.user_id == user.id)
        if status_filter is not None:
            stmt = stmt.where(TransferRequest.status == status_filter)
        if payment_state is not None:
            stmt = stmt.where(TransferRequest.payment_state == payment_state)
        if booking_id is not None:
            stmt = stmt.where(TransferRequest.booking_id == booking_id)
        return await paginated(self.db, stmt, limit=limit, offset=offset)

    async def create(
        self, payload: TransferRequestCreate, user: User, *, locale: str = "en"
    ) -> TransferRequest:
        """Standalone order. Priced at the current tariff when routed.

        Always lands as ``unpaid``: the booking it attaches to may already be
        paid, and re-opening a settled payment for an add-on is worse than
        collecting the difference offline.
        """
        owner_id = await resolve_owner_for_booking(
            self.db,
            booking_id=payload.booking_id,
            actor=user,
            resource_label="transfer request",
        )
        transfer = TransferRequest(
            user_id=owner_id,
            booking_id=payload.booking_id,
            direction=payload.direction,
            pickup_location=payload.pickup_location or "",
            dropoff_location=payload.dropoff_location or "",
            route_from_id=payload.route_from_id,
            route_to_id=payload.route_to_id,
            flight_number=payload.flight_number,
            flight_time=payload.flight_time,
            return_flight_number=payload.return_flight_number,
            return_flight_time=payload.return_flight_time,
            passengers_count=payload.passengers_count,
            vehicle_type=payload.vehicle_type,
            notes=payload.notes,
            contact_phone=payload.contact_phone,
            status=TransferStatus.REQUESTED,
            payment_state=TransferPaymentState.UNPAID,
        )

        if payload.route_from_id is not None and payload.route_to_id is not None:
            priced = await price_transfer(
                self.db,
                self.tariffs,
                route_from_id=payload.route_from_id,
                route_to_id=payload.route_to_id,
                vehicle_type=payload.vehicle_type,
                direction=payload.direction,
                locale=locale,
            )
            transfer.applied_tariff_id = priced.tariff_id
            transfer.applied_price = priced.price
            transfer.applied_currency = priced.currency
            transfer.commission_percent_snapshot = priced.commission_percent
            transfer.commission_amount_snapshot = priced.commission_amount
            transfer.pickup_location = payload.pickup_location or priced.pickup_location
            transfer.dropoff_location = (
                payload.dropoff_location or priced.dropoff_location
            )

        self.db.add(transfer)
        await self.db.commit()
        await self.db.refresh(transfer)
        return transfer

    async def apply_patch(
        self, transfer: TransferRequest, payload: TransferRequestUpdate, actor: User
    ) -> TransferRequest:
        data = payload.model_dump(exclude_unset=True)
        if is_transfer_operator(actor):
            return await self._operator_update(transfer, data)
        forbidden = sorted(set(data) - CUSTOMER_EDITABLE_FIELDS)
        if forbidden:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Only the transfer operator can change: {', '.join(forbidden)}",
            )
        return await self._customer_update(transfer, data)

    async def _operator_update(
        self, transfer: TransferRequest, data: dict
    ) -> TransferRequest:
        new_price = data.get("price", transfer.price)
        new_currency = data.get("currency", transfer.currency)
        if new_price is not None and new_currency is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="currency is required when price is set",
            )
        if data.get("vehicle_id") is not None:
            await self._assert_vehicle_assignable(data["vehicle_id"])

        was_confirmed = transfer.status == TransferStatus.CONFIRMED
        had_driver = bool(transfer.driver_name)

        for field, value in data.items():
            setattr(transfer, field, value)
        await self.db.commit()
        await self.db.refresh(transfer)

        await self._notify_operator_changes(
            transfer, was_confirmed=was_confirmed, had_driver=had_driver
        )
        return transfer

    async def _customer_update(
        self, transfer: TransferRequest, data: dict
    ) -> TransferRequest:
        if transfer.status in (TransferStatus.COMPLETED, TransferStatus.CANCELLED):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Transfer in status {transfer.status.value} can no longer "
                    "be edited"
                ),
            )
        for field, value in data.items():
            setattr(transfer, field, value)
        await self.db.commit()
        await self.db.refresh(transfer)
        return transfer

    async def cancel(self, transfer: TransferRequest, user: User) -> TransferRequest:
        if not is_transfer_operator(user) and transfer.user_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only cancel your own transfer requests",
            )
        if transfer.status not in _CANCELLABLE_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Transfer in status {transfer.status.value} cannot be cancelled"
                ),
            )
        transfer.status = TransferStatus.CANCELLED
        await self.db.commit()
        await self.db.refresh(transfer)
        return transfer

    async def _assert_vehicle_assignable(self, vehicle_id: uuid.UUID) -> None:
        vehicle = await self.db.get(TransferVehicle, vehicle_id)
        if vehicle is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Vehicle not found",
            )
        if not vehicle.is_active:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Vehicle is not active",
            )

    async def _notify_operator_changes(
        self, transfer: TransferRequest, *, was_confirmed: bool, had_driver: bool
    ) -> None:
        """Best-effort guest emails; the write is already committed."""
        newly_confirmed = (
            not was_confirmed and transfer.status == TransferStatus.CONFIRMED
        )
        driver_assigned = not had_driver and bool(transfer.driver_name)
        if not (newly_confirmed or driver_assigned):
            return

        email = await self.db.scalar(
            select(User.email).where(User.id == transfer.user_id)
        )
        if not email:
            return
        try:
            if newly_confirmed:
                send_transfer_confirmed(
                    to=email,
                    pickup_location=transfer.pickup_location,
                    dropoff_location=transfer.dropoff_location,
                    flight_time=transfer.flight_time,
                )
            if driver_assigned:
                send_transfer_driver_assigned(
                    to=email,
                    driver_name=transfer.driver_name or "",
                    driver_phone=transfer.driver_phone,
                    pickup_location=transfer.pickup_location,
                    dropoff_location=transfer.dropoff_location,
                )
        except Exception:  # pragma: no cover - notification must never block
            logger.exception("transfer notification failed for %s", transfer.id)


async def cancel_transfers_for_booking(db: AsyncSession, booking_id: uuid.UUID) -> None:
    """Cascade a booking cancellation onto its transfers.

    Caller owns the transaction — this only stages the rows so the cascade
    commits together with the booking status change.
    """
    transfers = (
        await db.scalars(
            select(TransferRequest).where(
                TransferRequest.booking_id == booking_id,
                TransferRequest.status != TransferStatus.CANCELLED,
            )
        )
    ).all()
    for transfer in transfers:
        transfer.status = TransferStatus.CANCELLED


def get_transfer_request_service(
    db: AsyncSession = Depends(get_db),
    tariffs: TransferTariffService = Depends(get_transfer_tariff_service),
) -> TransferRequestService:
    return TransferRequestService(db, tariffs)
