import uuid
from collections.abc import Sequence

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.pagination import paginated
from app.models.transfer_request import TransferRequest, VehicleType
from app.models.transfer_vehicle import TransferVehicle
from app.schemas.transfer_vehicle import TransferVehicleCreate, TransferVehicleUpdate


class TransferVehicleService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_all(
        self,
        *,
        limit: int,
        offset: int,
        is_active: bool | None = None,
        vehicle_type: VehicleType | None = None,
    ) -> tuple[Sequence[TransferVehicle], int]:
        stmt = select(TransferVehicle).order_by(TransferVehicle.created_at.asc())
        if is_active is not None:
            stmt = stmt.where(TransferVehicle.is_active.is_(is_active))
        if vehicle_type is not None:
            stmt = stmt.where(TransferVehicle.vehicle_type == vehicle_type)
        return await paginated(self.db, stmt, limit=limit, offset=offset)

    async def get_by_id(self, vehicle_id: uuid.UUID) -> TransferVehicle | None:
        return await self.db.get(TransferVehicle, vehicle_id)

    async def create(self, payload: TransferVehicleCreate) -> TransferVehicle:
        await self._assert_plate_free(payload.plate)
        vehicle = TransferVehicle(
            vehicle_type=payload.vehicle_type,
            capacity=payload.capacity,
            plate=payload.plate.strip(),
            label=payload.label,
            is_active=payload.is_active,
        )
        self.db.add(vehicle)
        await self.db.commit()
        await self.db.refresh(vehicle)
        return vehicle

    async def update(
        self, vehicle: TransferVehicle, payload: TransferVehicleUpdate
    ) -> TransferVehicle:
        data = payload.model_dump(exclude_unset=True)
        if "plate" in data and data["plate"] is not None:
            data["plate"] = data["plate"].strip()
            await self._assert_plate_free(data["plate"], exclude_id=vehicle.id)
        for field, value in data.items():
            setattr(vehicle, field, value)
        await self.db.commit()
        await self.db.refresh(vehicle)
        return vehicle

    async def delete(self, vehicle: TransferVehicle) -> None:
        assigned = await self.db.scalar(
            select(TransferRequest.id)
            .where(TransferRequest.vehicle_id == vehicle.id)
            .limit(1)
        )
        if assigned is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Vehicle is assigned to a transfer; "
                    "set is_active=false instead of deleting it"
                ),
            )
        await self.db.delete(vehicle)
        await self.db.commit()

    async def _assert_plate_free(
        self, plate: str, *, exclude_id: uuid.UUID | None = None
    ) -> None:
        stmt = select(TransferVehicle.id).where(TransferVehicle.plate == plate.strip())
        if exclude_id is not None:
            stmt = stmt.where(TransferVehicle.id != exclude_id)
        if await self.db.scalar(stmt.limit(1)) is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A vehicle with this plate already exists",
            )


def get_transfer_vehicle_service(
    db: AsyncSession = Depends(get_db),
) -> TransferVehicleService:
    return TransferVehicleService(db)
