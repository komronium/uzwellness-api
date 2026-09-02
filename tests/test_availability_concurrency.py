"""Two writers touching the same room-night must queue, not collide.

`room_availability` has a UNIQUE(room_id, date), and the rows are created
lazily on first write. Without a lock on the parent room, an admin who
double-clicks "Save" — or an admin blocking dates while a guest books them —
has both requests discover "no row yet" and both INSERT.
"""

import asyncio
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.availability import RoomAvailability
from app.models.sanatorium import SanatoriumStatus
from app.models.user import User
from app.schemas.room import AvailabilityBlock
from app.services.room_availability_service import RoomAvailabilityService
from tests.factories import make_room, make_sanatorium


async def test_simultaneous_blocks_do_not_collide(
    db: AsyncSession, session_factory, admin_user: User
) -> None:
    sanatorium = await make_sanatorium(
        db, status=SanatoriumStatus.APPROVED, admin_user_id=admin_user.id
    )
    room = await make_room(db, sanatorium=sanatorium, inventory_count=5)
    start = date.today() + timedelta(days=30)
    payload = AvailabilityBlock(
        date_from=start, date_to=start + timedelta(days=3), units_blocked=2
    )

    async def block() -> None:
        async with session_factory() as session:
            service = RoomAvailabilityService(session)
            room_copy = await session.get(type(room), room.id)
            await service.block_range(room_copy, payload, admin_user)

    # Both requests start before either commits — the classic double-click.
    await asyncio.gather(block(), block())

    rows = (
        await db.scalars(
            select(RoomAvailability).where(RoomAvailability.room_id == room.id)
        )
    ).all()
    assert len(rows) == 3
    assert {row.units_blocked for row in rows} == {2}
