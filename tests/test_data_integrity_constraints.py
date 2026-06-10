from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.availability import RoomAvailability
from app.models.booking import Booking, BookingStatus, BookingType
from app.models.package import Package
from app.models.program import TreatmentProgram
from app.models.rate_plan import RatePlan
from app.models.review import SanatoriumReview
from app.models.room import Room
from app.models.user import User
from tests.factories import make_room, make_sanatorium


async def _commit_fails(db: AsyncSession) -> None:
    with pytest.raises(IntegrityError):
        await db.commit()
    await db.rollback()


async def test_room_rejects_negative_inventory(db: AsyncSession) -> None:
    sanatorium = await make_sanatorium(db, slug="constraint-room")
    db.add(
        Room(
            sanatorium_id=sanatorium.id,
            name={"en": "Invalid Room"},
            capacity=2,
            inventory_count=-1,
            base_price=Decimal("100.00"),
            base_currency="USD",
            min_nights=1,
            markup_percent=Decimal("0"),
        )
    )

    await _commit_fails(db)


async def test_booking_rejects_invalid_dates(
    db: AsyncSession, customer_user: User
) -> None:
    sanatorium = await make_sanatorium(db, slug="constraint-booking")
    room = await make_room(db, sanatorium=sanatorium)
    db.add(
        Booking(
            user_id=customer_user.id,
            room_id=room.id,
            booking_type=BookingType.ROOM,
            check_in=date(2027, 1, 2),
            check_out=date(2027, 1, 2),
            guests=1,
            status=BookingStatus.CONFIRMED,
            final_price=Decimal("100.00"),
            currency="USD",
        )
    )

    await _commit_fails(db)


async def test_session_booking_allows_same_day_dates(
    db: AsyncSession, customer_user: User
) -> None:
    sanatorium = await make_sanatorium(db, slug="constraint-session-booking")
    program = TreatmentProgram(
        sanatorium_id=sanatorium.id,
        name={"en": "Doctor Visit"},
        price=Decimal("40.00"),
        currency="USD",
    )
    db.add(program)
    await db.flush()
    db.add(
        Booking(
            user_id=customer_user.id,
            program_id=program.id,
            booking_type=BookingType.SESSION,
            check_in=date(2027, 1, 2),
            check_out=date(2027, 1, 2),
            guests=1,
            status=BookingStatus.CONFIRMED,
            final_price=Decimal("40.00"),
            currency="USD",
        )
    )

    await db.commit()


async def test_rate_plan_rejects_invalid_discount_percent(
    db: AsyncSession,
) -> None:
    sanatorium = await make_sanatorium(db, slug="constraint-rate-plan")
    room = await make_room(db, sanatorium=sanatorium)
    db.add(
        RatePlan(
            room_id=room.id,
            name={"en": "Invalid Promo"},
            promo_percent=Decimal("150.00"),
        )
    )

    await _commit_fails(db)


async def test_room_availability_rejects_negative_units(
    db: AsyncSession,
) -> None:
    sanatorium = await make_sanatorium(db, slug="constraint-availability")
    room = await make_room(db, sanatorium=sanatorium)
    db.add(
        RoomAvailability(
            room_id=room.id,
            date=date(2027, 1, 1),
            units_blocked=-1,
            units_booked=0,
        )
    )

    await _commit_fails(db)


async def test_review_rejects_score_outside_ten_point_scale(
    db: AsyncSession,
) -> None:
    sanatorium = await make_sanatorium(db, slug="constraint-review")
    db.add(
        SanatoriumReview(
            sanatorium_id=sanatorium.id,
            reviewer_name="Guest",
            rating=11,
            body="Invalid score",
        )
    )

    await _commit_fails(db)


async def test_treatment_program_rejects_invalid_night_range(
    db: AsyncSession,
) -> None:
    sanatorium = await make_sanatorium(db, slug="constraint-treatment")
    db.add(
        TreatmentProgram(
            sanatorium_id=sanatorium.id,
            name={"en": "Invalid Stay Program"},
            min_nights=5,
            max_nights=3,
        )
    )

    await _commit_fails(db)


async def test_package_rejects_negative_base_price(db: AsyncSession) -> None:
    sanatorium = await make_sanatorium(db, slug="constraint-package")
    room = await make_room(db, sanatorium=sanatorium)
    db.add(
        Package(
            slug="invalid-package",
            title={"en": "Invalid Package"},
            duration_nights=3,
            base_price=Decimal("-1.00"),
            currency="USD",
            sanatorium_id=sanatorium.id,
            room_id=room.id,
        )
    )

    await _commit_fails(db)
