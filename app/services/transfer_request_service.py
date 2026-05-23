import uuid
from collections.abc import Sequence

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.booking_attachment import resolve_owner_for_booking
from app.core.database import get_db
from app.core.pagination import paginated
from app.models.transfer_request import TransferRequest, TransferStatus
from app.models.user import User, UserRole
from app.schemas.transfer_request import (
    TransferRequestCreate,
    TransferRequestUpdate,
)

_CANCELLABLE_STATUSES = {TransferStatus.REQUESTED, TransferStatus.CONFIRMED}


class TransferRequestService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(
        self, transfer_id: uuid.UUID
    ) -> TransferRequest | None:
        return await self.db.get(TransferRequest, transfer_id)

    async def get_visible(
        self, transfer_id: uuid.UUID, user: User
    ) -> TransferRequest | None:
        transfer = await self.get_by_id(transfer_id)
        if transfer is None:
            return None
        if user.role == UserRole.SUPER_ADMIN:
            return transfer
        if transfer.user_id == user.id:
            return transfer
        return None

    async def list_for_user(
        self,
        user: User,
        *,
        limit: int,
        offset: int,
        status_filter: TransferStatus | None = None,
    ) -> tuple[Sequence[TransferRequest], int]:
        stmt = select(TransferRequest).order_by(TransferRequest.created_at.desc())
        if user.role != UserRole.SUPER_ADMIN:
            stmt = stmt.where(TransferRequest.user_id == user.id)
        if status_filter is not None:
            stmt = stmt.where(TransferRequest.status == status_filter)
        return await paginated(self.db, stmt, limit=limit, offset=offset)

    async def create(
        self, payload: TransferRequestCreate, user: User
    ) -> TransferRequest:
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
            pickup_location=payload.pickup_location,
            dropoff_location=payload.dropoff_location,
            flight_number=payload.flight_number,
            flight_time=payload.flight_time,
            return_flight_number=payload.return_flight_number,
            return_flight_time=payload.return_flight_time,
            passengers_count=payload.passengers_count,
            vehicle_type=payload.vehicle_type,
            notes=payload.notes,
            contact_phone=payload.contact_phone,
            status=TransferStatus.REQUESTED,
        )
        self.db.add(transfer)
        await self.db.commit()
        await self.db.refresh(transfer)
        return transfer

    async def update(
        self, transfer: TransferRequest, payload: TransferRequestUpdate
    ) -> TransferRequest:
        data = payload.model_dump(exclude_unset=True)
        # If price is being set but currency would still be NULL, reject.
        new_price = data.get("price", transfer.price)
        new_currency = data.get("currency", transfer.currency)
        if new_price is not None and new_currency is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="currency is required when price is set",
            )
        for field, value in data.items():
            setattr(transfer, field, value)
        await self.db.commit()
        await self.db.refresh(transfer)
        return transfer

    async def cancel(
        self, transfer: TransferRequest, user: User
    ) -> TransferRequest:
        if (
            user.role != UserRole.SUPER_ADMIN
            and transfer.user_id != user.id
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only cancel your own transfer requests",
            )
        if transfer.status not in _CANCELLABLE_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Transfer in status {transfer.status.value} cannot be "
                    "cancelled"
                ),
            )
        transfer.status = TransferStatus.CANCELLED
        await self.db.commit()
        await self.db.refresh(transfer)
        return transfer


def get_transfer_request_service(
    db: AsyncSession = Depends(get_db),
) -> TransferRequestService:
    return TransferRequestService(db)
