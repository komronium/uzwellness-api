import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.pagination import paginated
from app.models.transfer_request import TransferDirection, VehicleType
from app.models.transfer_tariff import TransferTariff
from app.schemas.transfer_tariff import TransferTariffCreate
from app.services.transfer_location_service import (
    TransferLocationService,
    get_transfer_location_service,
)


@dataclass(slots=True)
class TransferQuote:
    """Price for one transfer job, resolved from the tariffs current *now*."""

    tariff_id: uuid.UUID
    price: Decimal
    currency: str


class TransferTariffService:
    def __init__(self, db: AsyncSession, locations: TransferLocationService) -> None:
        self.db = db
        self.locations = locations

    async def list_versions(
        self,
        *,
        limit: int,
        offset: int,
        route_from_id: uuid.UUID | None = None,
        route_to_id: uuid.UUID | None = None,
        vehicle_type: VehicleType | None = None,
        current_only: bool = False,
    ) -> tuple[Sequence[TransferTariff], int]:
        stmt = select(TransferTariff).order_by(TransferTariff.effective_from.desc())
        if route_from_id is not None:
            stmt = stmt.where(TransferTariff.route_from_id == route_from_id)
        if route_to_id is not None:
            stmt = stmt.where(TransferTariff.route_to_id == route_to_id)
        if vehicle_type is not None:
            stmt = stmt.where(TransferTariff.vehicle_type == vehicle_type)
        if current_only:
            stmt = stmt.where(TransferTariff.effective_to.is_(None))
        return await paginated(self.db, stmt, limit=limit, offset=offset)

    async def current(
        self,
        *,
        route_from_id: uuid.UUID,
        route_to_id: uuid.UUID,
        vehicle_type: VehicleType,
        for_update: bool = False,
    ) -> TransferTariff | None:
        stmt = select(TransferTariff).where(
            TransferTariff.route_from_id == route_from_id,
            TransferTariff.route_to_id == route_to_id,
            TransferTariff.vehicle_type == vehicle_type,
            TransferTariff.effective_to.is_(None),
        )
        if for_update:
            stmt = stmt.with_for_update()
        return await self.db.scalar(stmt)

    async def create(self, payload: TransferTariffCreate) -> TransferTariff:
        """Insert a new price version, closing the previous one atomically."""
        await self.locations.require(payload.route_from_id, label="route_from_id")
        await self.locations.require(payload.route_to_id, label="route_to_id")

        now = datetime.now(UTC)
        previous = await self.current(
            route_from_id=payload.route_from_id,
            route_to_id=payload.route_to_id,
            vehicle_type=payload.vehicle_type,
            for_update=True,
        )
        if previous is not None:
            previous.effective_to = now

        tariff = TransferTariff(
            route_from_id=payload.route_from_id,
            route_to_id=payload.route_to_id,
            vehicle_type=payload.vehicle_type,
            price=payload.price,
            currency=payload.currency,
            effective_from=now,
        )
        self.db.add(tariff)
        await self.db.commit()
        await self.db.refresh(tariff)
        return tariff

    async def quote(
        self,
        *,
        route_from_id: uuid.UUID,
        route_to_id: uuid.UUID,
        vehicle_type: VehicleType,
        direction: TransferDirection,
    ) -> TransferQuote:
        """Total price for the direction, summing both legs on a round trip.

        A round trip is priced as the outbound tariff plus the tariff of the
        reversed route, so operators keep a single price table instead of a
        third route dimension.
        """
        outbound = await self._require_current(
            route_from_id=route_from_id,
            route_to_id=route_to_id,
            vehicle_type=vehicle_type,
        )
        if direction != TransferDirection.ROUND_TRIP:
            return TransferQuote(
                tariff_id=outbound.id,
                price=outbound.price,
                currency=outbound.currency,
            )

        inbound = await self._require_current(
            route_from_id=route_to_id,
            route_to_id=route_from_id,
            vehicle_type=vehicle_type,
        )
        if inbound.currency != outbound.currency:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={
                    "code": "tariff_currency_mismatch",
                    "message": (
                        "The two legs of this round trip are priced in "
                        f"{outbound.currency} and {inbound.currency}"
                    ),
                },
            )
        return TransferQuote(
            tariff_id=outbound.id,
            price=outbound.price + inbound.price,
            currency=outbound.currency,
        )

    async def _require_current(
        self,
        *,
        route_from_id: uuid.UUID,
        route_to_id: uuid.UUID,
        vehicle_type: VehicleType,
    ) -> TransferTariff:
        tariff = await self.current(
            route_from_id=route_from_id,
            route_to_id=route_to_id,
            vehicle_type=vehicle_type,
        )
        if tariff is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={
                    "code": "no_tariff_for_route",
                    "route_from_id": str(route_from_id),
                    "route_to_id": str(route_to_id),
                    "vehicle_type": vehicle_type.value,
                },
            )
        return tariff


def get_transfer_tariff_service(
    db: AsyncSession = Depends(get_db),
    locations: TransferLocationService = Depends(get_transfer_location_service),
) -> TransferTariffService:
    return TransferTariffService(db, locations)
