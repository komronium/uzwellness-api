from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Protocol

from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.booking import Booking


class BookingRepository(Protocol):
    async def get(self, booking_id: uuid.UUID) -> Booking | None: ...
    async def get_with_extras(self, booking_id: uuid.UUID) -> Booking | None: ...
    async def add(self, booking: Booking) -> None: ...
    async def find_one_filtered(
        self,
        *,
        booking_id: uuid.UUID,
        base_filters: list,
    ) -> Booking | None: ...
    async def list_filtered(
        self,
        *,
        base_filters: list,
        limit: int,
        offset: int,
    ) -> tuple[Sequence[Booking], int]: ...


class SqlBookingRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, booking_id: uuid.UUID) -> Booking | None:
        return await self.db.get(Booking, booking_id)

    async def get_with_extras(self, booking_id: uuid.UUID) -> Booking | None:
        stmt = (
            select(Booking)
            .options(
                selectinload(Booking.extra_beds),
                selectinload(Booking.user),
                selectinload(Booking.payments),
            )
            .where(Booking.id == booking_id)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def add(self, booking: Booking) -> None:
        self.db.add(booking)

    async def find_one_filtered(
        self,
        *,
        booking_id: uuid.UUID,
        base_filters: list,
    ) -> Booking | None:
        stmt = (
            select(Booking)
            .options(
                selectinload(Booking.extra_beds),
                selectinload(Booking.user),
                selectinload(Booking.payments),
            )
            .where(Booking.id == booking_id)
        )
        for clause in base_filters:
            stmt = stmt.where(clause)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def list_filtered(
        self,
        *,
        base_filters: list,
        limit: int,
        offset: int,
    ) -> tuple[Sequence[Booking], int]:
        base = select(Booking)
        for clause in base_filters:
            base = base.where(clause)
        total = (
            await self.db.execute(select(func.count()).select_from(base.subquery()))
        ).scalar_one()
        stmt = (
            base.options(
                selectinload(Booking.extra_beds),
                selectinload(Booking.user),
                selectinload(Booking.payments),
            )
            .order_by(Booking.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        return rows, total


def get_booking_repository(
    db: AsyncSession = Depends(get_db),
) -> BookingRepository:
    return SqlBookingRepository(db)
