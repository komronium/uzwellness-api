import calendar
import re
import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import not_found
from app.core.database import get_db
from app.models.availability import RoomAvailability
from app.models.room import Room
from app.models.sanatorium import Sanatorium, SanatoriumStatus

router = APIRouter(prefix="/availability", tags=["availability"])

_MONTH_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


def _parse_month(value: str) -> tuple[date, date]:
    match = _MONTH_RE.match(value)
    if match is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="month must be in YYYY-MM format",
        )
    year, month = int(match.group(1)), int(match.group(2))
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


@router.get("")
async def get_availability(
    sanatorium_id: uuid.UUID = Query(...),
    month: str = Query(..., description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    first, last = _parse_month(month)

    sanatorium = (
        await db.execute(
            select(Sanatorium).where(
                Sanatorium.id == sanatorium_id,
                Sanatorium.status == SanatoriumStatus.APPROVED,
            )
        )
    ).scalar_one_or_none()
    if sanatorium is None:
        raise not_found("Sanatorium not found")

    # Total inventory across active rooms of the sanatorium.
    total_inventory = (
        await db.execute(
            select(func.coalesce(func.sum(Room.inventory_count), 0)).where(
                Room.sanatorium_id == sanatorium_id,
                Room.is_active.is_(True),
            )
        )
    ).scalar_one()

    # Per-day blocked + booked across active rooms.
    stmt = (
        select(
            RoomAvailability.date,
            func.sum(
                RoomAvailability.units_blocked + RoomAvailability.units_booked
            ).label("used"),
        )
        .join(Room, RoomAvailability.room_id == Room.id)
        .where(
            Room.sanatorium_id == sanatorium_id,
            Room.is_active.is_(True),
            RoomAvailability.date >= first,
            RoomAvailability.date <= last,
        )
        .group_by(RoomAvailability.date)
    )
    used_per_date = {
        row.date: int(row.used) for row in (await db.execute(stmt)).all()
    }

    dates: dict[str, dict] = {}
    current = first
    while current <= last:
        used = used_per_date.get(current, 0)
        rooms_left = max(int(total_inventory) - used, 0)
        if total_inventory == 0:
            dates[current.isoformat()] = {"available": False}
        elif rooms_left <= 0:
            dates[current.isoformat()] = {"available": False, "rooms_left": 0}
        else:
            dates[current.isoformat()] = {"available": True, "rooms_left": rooms_left}
        current += timedelta(days=1)

    return {"dates": dates}
