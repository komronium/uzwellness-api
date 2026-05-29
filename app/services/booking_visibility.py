import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking
from app.models.package import Package
from app.models.program import TreatmentProgram
from app.models.room import Room
from app.models.sanatorium import Sanatorium
from app.models.user import User, UserRole


def booking_visibility_clauses(user: User) -> list:
    if user.role == UserRole.SUPER_ADMIN:
        return []
    if user.role == UserRole.ADMIN:
        room_subquery = (
            select(Room.id)
            .join(Sanatorium, Room.sanatorium_id == Sanatorium.id)
            .where(Sanatorium.admin_user_id == user.id)
            .scalar_subquery()
        )
        program_subquery = (
            select(TreatmentProgram.id)
            .join(Sanatorium, TreatmentProgram.sanatorium_id == Sanatorium.id)
            .where(Sanatorium.admin_user_id == user.id)
            .scalar_subquery()
        )
        package_subquery = (
            select(Package.id)
            .join(Sanatorium, Package.sanatorium_id == Sanatorium.id)
            .where(Sanatorium.admin_user_id == user.id)
            .scalar_subquery()
        )
        return [
            Booking.room_id.in_(room_subquery)
            | Booking.program_id.in_(program_subquery)
            | Booking.package_id.in_(package_subquery)
        ]
    return [Booking.user_id == user.id]


async def admin_owns_booking_sanatorium(
    db: AsyncSession, booking: Booking, admin_id: uuid.UUID
) -> bool:
    sanatorium_id: uuid.UUID | None = None
    if booking.room_id is not None:
        sanatorium_id = await db.scalar(
            select(Room.sanatorium_id).where(Room.id == booking.room_id)
        )
    elif booking.program_id is not None:
        sanatorium_id = await db.scalar(
            select(TreatmentProgram.sanatorium_id).where(
                TreatmentProgram.id == booking.program_id
            )
        )
    elif booking.package_id is not None:
        sanatorium_id = await db.scalar(
            select(Package.sanatorium_id).where(Package.id == booking.package_id)
        )

    if sanatorium_id is None:
        return False
    owner_id = await db.scalar(
        select(Sanatorium.admin_user_id).where(Sanatorium.id == sanatorium_id)
    )
    return owner_id == admin_id
