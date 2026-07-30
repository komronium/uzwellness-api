import uuid
from collections.abc import Sequence

from fastapi import Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.pagination import paginated
from app.core.utils import merge_translation_fields
from app.models.transfer_location import TransferLocation, TransferLocationKind
from app.models.transfer_request import TransferRequest
from app.models.transfer_tariff import TransferTariff
from app.schemas.transfer_location import (
    TransferLocationCreate,
    TransferLocationUpdate,
)


class TransferLocationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_all(
        self,
        *,
        limit: int,
        offset: int,
        is_active: bool | None = None,
        kind: TransferLocationKind | None = None,
    ) -> tuple[Sequence[TransferLocation], int]:
        stmt = select(TransferLocation).order_by(TransferLocation.created_at.asc())
        if is_active is not None:
            stmt = stmt.where(TransferLocation.is_active.is_(is_active))
        if kind is not None:
            stmt = stmt.where(TransferLocation.kind == kind)
        return await paginated(self.db, stmt, limit=limit, offset=offset)

    async def get_by_id(self, location_id: uuid.UUID) -> TransferLocation | None:
        return await self.db.get(TransferLocation, location_id)

    async def require(self, location_id: uuid.UUID, *, label: str) -> TransferLocation:
        location = await self.get_by_id(location_id)
        if location is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"{label} is not a known transfer location",
            )
        return location

    async def create(self, payload: TransferLocationCreate) -> TransferLocation:
        location = TransferLocation(
            name=payload.name.model_dump(),
            kind=payload.kind,
            is_active=payload.is_active,
        )
        self.db.add(location)
        await self.db.commit()
        await self.db.refresh(location)
        return location

    async def update(
        self, location: TransferLocation, payload: TransferLocationUpdate
    ) -> TransferLocation:
        data = payload.model_dump(exclude_unset=True)
        merge_translation_fields(location, data, ("name",))
        for field, value in data.items():
            setattr(location, field, value)
        await self.db.commit()
        await self.db.refresh(location)
        return location

    async def delete(self, location: TransferLocation) -> None:
        if await self._is_referenced(location.id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Location is used by a tariff or transfer; "
                    "set is_active=false instead of deleting it"
                ),
            )
        await self.db.delete(location)
        await self.db.commit()

    async def _is_referenced(self, location_id: uuid.UUID) -> bool:
        tariff_id = await self.db.scalar(
            select(TransferTariff.id)
            .where(
                or_(
                    TransferTariff.route_from_id == location_id,
                    TransferTariff.route_to_id == location_id,
                )
            )
            .limit(1)
        )
        if tariff_id is not None:
            return True
        transfer_id = await self.db.scalar(
            select(TransferRequest.id)
            .where(
                or_(
                    TransferRequest.route_from_id == location_id,
                    TransferRequest.route_to_id == location_id,
                )
            )
            .limit(1)
        )
        return transfer_id is not None


def get_transfer_location_service(
    db: AsyncSession = Depends(get_db),
) -> TransferLocationService:
    return TransferLocationService(db)
