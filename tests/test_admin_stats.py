from __future__ import annotations

from datetime import date
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking, BookingStatus, BookingType
from app.models.program import TreatmentProgram
from app.models.user import User
from tests.factories import make_room, make_sanatorium


async def test_admin_stats_top_sanatoriums_include_session_bookings(
    client: AsyncClient,
    db: AsyncSession,
    customer_user: User,
    super_admin_headers: dict,
) -> None:
    treatment_sanatorium = await make_sanatorium(
        db, name={"en": "Treatment Leader"}, slug="treatment-leader"
    )
    room_sanatorium = await make_sanatorium(
        db, name={"en": "Room Seller"}, slug="room-seller"
    )
    program = TreatmentProgram(
        sanatorium_id=treatment_sanatorium.id,
        name={"en": "Doctor Visit"},
        price=Decimal("300.00"),
        currency="USD",
    )
    room = await make_room(db, sanatorium=room_sanatorium, base_price="100.00")
    db.add(program)
    await db.flush()
    db.add_all(
        [
            Booking(
                user_id=customer_user.id,
                program_id=program.id,
                booking_type=BookingType.SESSION,
                check_in=date(2027, 1, 2),
                check_out=date(2027, 1, 2),
                guests=1,
                status=BookingStatus.CONFIRMED,
                final_price=Decimal("300.00"),
                currency="USD",
            ),
            Booking(
                user_id=customer_user.id,
                room_id=room.id,
                booking_type=BookingType.ROOM,
                check_in=date(2027, 1, 2),
                check_out=date(2027, 1, 3),
                guests=1,
                status=BookingStatus.CONFIRMED,
                final_price=Decimal("100.00"),
                currency="USD",
            ),
        ]
    )
    await db.commit()

    resp = await client.get("/api/admin/stats", headers=super_admin_headers)

    assert resp.status_code == 200, resp.text
    top = resp.json()["top_sanatoriums"]
    assert top[0]["id"] == str(treatment_sanatorium.id)
    assert top[0]["booking_count"] == 1
    assert top[0]["revenue"] == "300.00"
