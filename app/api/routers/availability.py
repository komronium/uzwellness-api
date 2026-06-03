import calendar
import re
import uuid
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, not_found, require_roles
from app.core.database import get_db
from app.core.pagination import Pagination
from app.models.availability import RoomAvailability
from app.models.availability_log import AvailabilityLogCategory
from app.models.room import Room
from app.models.sanatorium import Sanatorium, SanatoriumStatus
from app.models.user import UserRole
from app.schemas.availability_calendar import AvailabilityCalendarRead
from app.schemas.availability_log import (
    AvailabilityOperationLogList,
    AvailabilityOperationLogRead,
)
from app.schemas.bulk_availability import (
    BulkAllotmentUpdate,
    BulkCopyRates,
    BulkOperationResult,
    BulkRatesUpdate,
    BulkRestrictionsUpdate,
    BulkRoomStatusUpdate,
)
from app.services.availability_calendar_service import (
    AvailabilityCalendarService,
    get_availability_calendar_service,
)
from app.services.availability_log_service import (
    AvailabilityLogService,
    get_availability_log_service,
)
from app.services.bulk_availability_service import (
    BulkAvailabilityService,
    get_bulk_availability_service,
)

router = APIRouter(prefix="/availability", tags=["Availability"])
require_admin_or_above = require_roles(UserRole.ADMIN, UserRole.SUPER_ADMIN)

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

    sanatorium = await db.scalar(
        select(Sanatorium).where(
            Sanatorium.id == sanatorium_id,
            Sanatorium.status == SanatoriumStatus.APPROVED,
        )
    )
    if sanatorium is None:
        raise not_found("Sanatorium not found")

    total_inventory = await db.scalar(
        select(func.coalesce(func.sum(Room.inventory_count), 0)).where(
            Room.sanatorium_id == sanatorium_id,
            Room.is_active.is_(True),
            Room.deleted_at.is_(None),
        )
    )

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
            Room.deleted_at.is_(None),
            RoomAvailability.date >= first,
            RoomAvailability.date <= last,
        )
        .group_by(RoomAvailability.date)
    )
    used_per_date = {row.date: int(row.used) for row in (await db.execute(stmt)).all()}

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


@router.get(
    "/calendar",
    response_model=AvailabilityCalendarRead,
    dependencies=[Depends(require_admin_or_above)],
)
async def get_admin_availability_calendar(
    current_user: CurrentUser,
    sanatorium_id: uuid.UUID = Query(...),
    date_from: date = Query(..., alias="from"),
    date_to: date = Query(..., alias="to"),
    room_id: uuid.UUID | None = Query(default=None),
    rate_plan_ids: list[uuid.UUID] | None = Query(default=None),
    calendar_service: AvailabilityCalendarService = Depends(
        get_availability_calendar_service
    ),
) -> AvailabilityCalendarRead:
    return await calendar_service.get_calendar(
        sanatorium_id=sanatorium_id,
        date_from=date_from,
        date_to=date_to,
        user=current_user,
        room_id=room_id,
        rate_plan_ids=rate_plan_ids,
    )


@router.get(
    "/logs",
    response_model=AvailabilityOperationLogList,
    dependencies=[Depends(require_admin_or_above)],
)
async def list_availability_logs(
    current_user: CurrentUser,
    page: Pagination,
    sanatorium_id: uuid.UUID = Query(...),
    room_id: uuid.UUID | None = Query(default=None),
    rate_plan_id: uuid.UUID | None = Query(default=None),
    category: AvailabilityLogCategory | None = Query(default=None),
    check_in_from: date | None = Query(default=None),
    check_in_to: date | None = Query(default=None),
    operated_from: datetime | None = Query(default=None),
    operated_to: datetime | None = Query(default=None),
    logs: AvailabilityLogService = Depends(get_availability_log_service),
) -> AvailabilityOperationLogList:
    items, total = await logs.list_for_sanatorium(
        sanatorium_id,
        current_user,
        room_id=room_id,
        rate_plan_id=rate_plan_id,
        category=category,
        check_in_from=check_in_from,
        check_in_to=check_in_to,
        operated_from=operated_from,
        operated_to=operated_to,
        limit=page.limit,
        offset=page.offset,
    )
    return AvailabilityOperationLogList(
        items=[AvailabilityOperationLogRead.from_obj(item) for item in items],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.post(
    "/bulk/allotment",
    response_model=BulkOperationResult,
    dependencies=[Depends(require_admin_or_above)],
)
async def bulk_update_allotment(
    payload: BulkAllotmentUpdate,
    current_user: CurrentUser,
    bulk: BulkAvailabilityService = Depends(get_bulk_availability_service),
) -> BulkOperationResult:
    return await bulk.update_allotment(payload, current_user)


@router.post(
    "/bulk/rates",
    response_model=BulkOperationResult,
    dependencies=[Depends(require_admin_or_above)],
)
async def bulk_update_rates(
    payload: BulkRatesUpdate,
    current_user: CurrentUser,
    bulk: BulkAvailabilityService = Depends(get_bulk_availability_service),
) -> BulkOperationResult:
    return await bulk.update_rates(payload, current_user)


@router.post(
    "/bulk/status",
    response_model=BulkOperationResult,
    dependencies=[Depends(require_admin_or_above)],
)
async def bulk_update_status(
    payload: BulkRoomStatusUpdate,
    current_user: CurrentUser,
    bulk: BulkAvailabilityService = Depends(get_bulk_availability_service),
) -> BulkOperationResult:
    return await bulk.update_status(payload, current_user)


@router.post(
    "/bulk/restrictions",
    response_model=BulkOperationResult,
    dependencies=[Depends(require_admin_or_above)],
)
async def bulk_update_restrictions(
    payload: BulkRestrictionsUpdate,
    current_user: CurrentUser,
    bulk: BulkAvailabilityService = Depends(get_bulk_availability_service),
) -> BulkOperationResult:
    return await bulk.update_restrictions(payload, current_user)


@router.post(
    "/bulk/copy-rates",
    response_model=BulkOperationResult,
    dependencies=[Depends(require_admin_or_above)],
)
async def bulk_copy_rates(
    payload: BulkCopyRates,
    current_user: CurrentUser,
    bulk: BulkAvailabilityService = Depends(get_bulk_availability_service),
) -> BulkOperationResult:
    return await bulk.copy_rates(payload, current_user)
