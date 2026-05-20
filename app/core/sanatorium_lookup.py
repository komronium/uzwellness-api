from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils import pick_locale
from app.models.booking import Booking
from app.models.package import Package
from app.models.program import TreatmentProgram
from app.models.room import Room
from app.models.sanatorium import Sanatorium


async def sanatorium_name_for_booking(db: AsyncSession, booking: Booking) -> str | None:
    """Resolve a display name for the sanatorium behind a booking.

    For package bookings without a linked sanatorium, falls back to the
    package title.
    """
    name_dict: dict | None = None
    if booking.room_id is not None:
        name_dict = (
            await db.execute(
                select(Sanatorium.name)
                .join(Room, Room.sanatorium_id == Sanatorium.id)
                .where(Room.id == booking.room_id)
            )
        ).scalar_one_or_none()
    elif booking.program_id is not None:
        name_dict = (
            await db.execute(
                select(Sanatorium.name)
                .join(
                    TreatmentProgram,
                    TreatmentProgram.sanatorium_id == Sanatorium.id,
                )
                .where(TreatmentProgram.id == booking.program_id)
            )
        ).scalar_one_or_none()
    elif booking.package_id is not None:
        row = (
            await db.execute(
                select(Package.title, Sanatorium.name)
                .select_from(Package)
                .join(
                    Sanatorium,
                    Sanatorium.id == Package.sanatorium_id,
                    isouter=True,
                )
                .where(Package.id == booking.package_id)
            )
        ).one_or_none()
        if row is not None:
            package_title, sanatorium_name = row
            name_dict = sanatorium_name or package_title
    if name_dict is None:
        return None
    return pick_locale(name_dict) or None
