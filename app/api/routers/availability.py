import calendar
import re
import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import CurrentUser, require_roles
from app.core.pagination import Pagination
from app.models.availability_log import AvailabilityLogCategory
from app.models.user import UserRole
from app.schemas.availability_calendar import (
    AvailabilityCalendarRead,
    PublicMonthAvailability,
)
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


@router.get(
    "",
    response_model=PublicMonthAvailability,
    response_model_exclude_none=True,
)
async def get_availability(
    sanatorium_id: uuid.UUID = Query(...),
    month: str = Query(..., description="YYYY-MM"),
    calendar_service: AvailabilityCalendarService = Depends(
        get_availability_calendar_service
    ),
) -> PublicMonthAvailability:
    first, last = _parse_month(month)
    return await calendar_service.get_public_month(
        sanatorium_id=sanatorium_id, first=first, last=last
    )


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
