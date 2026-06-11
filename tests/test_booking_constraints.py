"""Tests for the room_id XOR program_id DB constraint on Booking."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking, BookingStatus, BookingType


@pytest.fixture
async def fresh_db(db):
    return db


class TestBookingXorConstraint:
    async def test_neither_room_nor_program_violates(self, db: AsyncSession):
        b = Booking(
            user_id=uuid.uuid4(),
            booking_type=BookingType.ROOM,
            check_in=date(2027, 1, 1),
            check_out=date(2027, 1, 2),
            guests=1,
            status=BookingStatus.CONFIRMED,
            final_price=Decimal("100"),
            currency="USD",
        )
        db.add(b)
        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()

    async def test_both_room_and_program_violates(self, db: AsyncSession):
        b = Booking(
            user_id=uuid.uuid4(),
            room_id=uuid.uuid4(),
            program_id=uuid.uuid4(),
            booking_type=BookingType.ROOM,
            check_in=date(2027, 1, 1),
            check_out=date(2027, 1, 2),
            guests=1,
            status=BookingStatus.CONFIRMED,
            final_price=Decimal("100"),
            currency="USD",
        )
        db.add(b)
        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()
