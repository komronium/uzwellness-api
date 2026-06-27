import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    ConverterDep,
    CurrentUser,
    LocaleDep,
    not_found,
    require_roles,
)
from app.core.currency import CurrencyConverter
from app.api.rate_limits import booking_rate_limit
from app.core.database import get_db
from app.core.pagination import Pagination
from app.models.booking import Booking, BookingStatus
from app.models.cancellation import CancellationStatus
from app.models.user import User, UserRole
from app.schemas.booking import (
    AdminReservationDashboard,
    BookingCreate,
    BookingCustomerRead,
    BookingDateFilter,
    BookingList,
    BookingRead,
    InvoiceRead,
    RoomOfferBookingCreate,
)
from app.schemas.cancellation import CancellationConfirm, CancellationRequestRead
from app.services.admin_reservation_service import (
    AdminReservationService,
    get_admin_reservation_service,
)
from app.services.booking_invoice import build_invoice
from app.services.booking_notifications import send_booking_confirmation_email
from app.services.booking_service import BookingService, get_booking_service
from app.services.booking_voucher import build_voucher_pdf
from app.services.cancellation_service import (
    CancellationService,
    active_cancellation_status_map,
    get_cancellation_service,
)
from app.services.room_offer_booking_service import (
    RoomOfferBookingService,
    get_room_offer_booking_service,
)

router = APIRouter(prefix="/bookings", tags=["Bookings"])

_ADMIN_ROLES = {UserRole.ADMIN, UserRole.SUPER_ADMIN}
require_admin_or_above = require_roles(UserRole.ADMIN, UserRole.SUPER_ADMIN)


def _to_read(
    booking: Booking,
    viewer: User,
    converter: CurrencyConverter | None = None,
    cancellation_status: CancellationStatus | None = None,
) -> BookingRead:
    data = BookingRead.model_validate(booking)
    data.cancellation_status = cancellation_status
    if viewer.role in _ADMIN_ROLES and booking.user is not None:
        data.customer = BookingCustomerRead.model_validate(booking.user)
    if converter is not None:
        data.display_price = converter.convert(booking.final_price, booking.currency)
        data.display_currency = converter.target
    return data


@router.post(
    "",
    response_model=BookingRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(booking_rate_limit)],
)
async def create_booking(
    payload: BookingCreate,
    current_user: CurrentUser,
    locale: LocaleDep,
    converter: ConverterDep,
    bookings: BookingService = Depends(get_booking_service),
    db: AsyncSession = Depends(get_db),
) -> BookingRead:
    booking = await bookings.create(payload, current_user)
    await send_booking_confirmation_email(db, booking, locale)
    return _to_read(booking, current_user, converter)


@router.post(
    "/room-offer",
    response_model=BookingRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(booking_rate_limit)],
)
async def create_room_offer_booking(
    payload: RoomOfferBookingCreate,
    current_user: CurrentUser,
    locale: LocaleDep,
    converter: ConverterDep,
    bookings: RoomOfferBookingService = Depends(get_room_offer_booking_service),
    db: AsyncSession = Depends(get_db),
) -> BookingRead:
    booking = await bookings.create(payload, current_user, locale=locale)
    await send_booking_confirmation_email(db, booking, locale)
    return _to_read(booking, current_user, converter)


@router.get("", response_model=BookingList)
async def list_bookings(
    current_user: CurrentUser,
    converter: ConverterDep,
    page: Pagination,
    is_b2b: bool | None = Query(default=None),
    agent_id: uuid.UUID | None = Query(default=None),
    q: str | None = Query(default=None, max_length=200),
    status_filter: BookingStatus | None = Query(default=None, alias="status"),
    is_processed: bool | None = Query(default=None),
    cancellation_status: CancellationStatus | None = Query(default=None),
    date_filter: BookingDateFilter = Query(default=BookingDateFilter.BOOKING_DATE),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    bookings: BookingService = Depends(get_booking_service),
    db: AsyncSession = Depends(get_db),
) -> BookingList:
    items, total = await bookings.list_for_user(
        current_user,
        limit=page.limit,
        offset=page.offset,
        is_b2b=is_b2b,
        agent_id=agent_id,
        q=q,
        status_filter=status_filter,
        is_processed=is_processed,
        cancellation_status=cancellation_status,
        date_filter=date_filter,
        date_from=date_from,
        date_to=date_to,
    )
    cancel_map = await active_cancellation_status_map(db, [b.id for b in items])
    return BookingList(
        items=[
            _to_read(b, current_user, converter, cancel_map.get(b.id)) for b in items
        ],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get(
    "/dashboard",
    response_model=AdminReservationDashboard,
    dependencies=[Depends(require_admin_or_above)],
)
async def reservation_dashboard(
    current_user: CurrentUser,
    activity_date: date | None = Query(default=None),
    unprocessed_limit: int = Query(default=5, ge=1, le=20),
    admin_reservations: AdminReservationService = Depends(
        get_admin_reservation_service
    ),
) -> AdminReservationDashboard:
    return await admin_reservations.dashboard(
        current_user,
        activity_date=activity_date,
        unprocessed_limit=unprocessed_limit,
    )


@router.get("/by-number/{reservation_number}", response_model=BookingRead)
async def get_booking_by_reservation_number(
    reservation_number: str,
    current_user: CurrentUser,
    converter: ConverterDep,
    bookings: BookingService = Depends(get_booking_service),
    db: AsyncSession = Depends(get_db),
) -> BookingRead:
    booking = await bookings.get_visible_by_reservation_number(
        reservation_number, current_user
    )
    if booking is None:
        raise not_found("Booking not found")
    cancel_map = await active_cancellation_status_map(db, [booking.id])
    return _to_read(booking, current_user, converter, cancel_map.get(booking.id))


@router.get("/{booking_id}", response_model=BookingRead)
async def get_booking(
    booking_id: str,
    current_user: CurrentUser,
    converter: ConverterDep,
    bookings: BookingService = Depends(get_booking_service),
    db: AsyncSession = Depends(get_db),
) -> BookingRead:
    booking = await bookings.get_visible_by_reference(booking_id, current_user)
    if booking is None:
        raise not_found("Booking not found")
    cancel_map = await active_cancellation_status_map(db, [booking.id])
    return _to_read(booking, current_user, converter, cancel_map.get(booking.id))


@router.patch(
    "/{booking_id}/process",
    response_model=BookingRead,
    dependencies=[Depends(require_admin_or_above)],
)
async def process_booking(
    booking_id: uuid.UUID,
    current_user: CurrentUser,
    converter: ConverterDep,
    bookings: BookingService = Depends(get_booking_service),
) -> BookingRead:
    booking = await bookings.get_visible(booking_id, current_user)
    if booking is None:
        raise not_found("Booking not found")
    processed = await bookings.mark_processed(booking, current_user)
    return _to_read(processed, current_user, converter)


@router.get("/{booking_id}/invoice", response_model=InvoiceRead)
async def get_booking_invoice(
    booking_id: uuid.UUID,
    current_user: CurrentUser,
    bookings: BookingService = Depends(get_booking_service),
    db: AsyncSession = Depends(get_db),
) -> InvoiceRead:
    booking = await bookings.get_visible(booking_id, current_user)
    if booking is None:
        raise not_found("Booking not found")
    data = await build_invoice(db, booking)
    return InvoiceRead(**data)


@router.get("/{booking_id}/voucher.pdf")
async def get_booking_voucher(
    booking_id: uuid.UUID,
    current_user: CurrentUser,
    locale: LocaleDep,
    bookings: BookingService = Depends(get_booking_service),
    db: AsyncSession = Depends(get_db),
) -> Response:
    booking = await bookings.get_visible(booking_id, current_user)
    if booking is None:
        raise not_found("Booking not found")
    pdf = await build_voucher_pdf(db, booking, locale)
    filename = f"Booking #{booking.reservation_number}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{booking_id}/cancel", response_model=BookingRead)
@router.patch("/{booking_id}/cancel", response_model=BookingRead, deprecated=True)
async def cancel_booking(
    booking_id: uuid.UUID,
    current_user: CurrentUser,
    converter: ConverterDep,
    bookings: BookingService = Depends(get_booking_service),
) -> BookingRead:
    booking = await bookings.get_visible(booking_id, current_user)
    if booking is None:
        raise not_found("Booking not found")
    cancelled = await bookings.cancel(booking, current_user)
    return _to_read(cancelled, current_user, converter)


# ── Cancellation by emailed code (customer) + admin approval ──────────────────


@router.post(
    "/{booking_id}/cancellation/request",
    response_model=CancellationRequestRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_cancellation_code(
    booking_id: uuid.UUID,
    current_user: CurrentUser,
    bookings: BookingService = Depends(get_booking_service),
    cancellations: CancellationService = Depends(get_cancellation_service),
) -> CancellationRequestRead:
    booking = await bookings.get_visible(booking_id, current_user)
    if booking is None:
        raise not_found("Booking not found")
    request = await cancellations.request_code(booking, current_user)
    return CancellationRequestRead.model_validate(request)


@router.post(
    "/{booking_id}/cancellation/confirm",
    response_model=CancellationRequestRead,
)
async def confirm_cancellation_code(
    booking_id: uuid.UUID,
    payload: CancellationConfirm,
    current_user: CurrentUser,
    bookings: BookingService = Depends(get_booking_service),
    cancellations: CancellationService = Depends(get_cancellation_service),
) -> CancellationRequestRead:
    booking = await bookings.get_visible(booking_id, current_user)
    if booking is None:
        raise not_found("Booking not found")
    request = await cancellations.confirm_code(booking, current_user, payload.code)
    return CancellationRequestRead.model_validate(request)


@router.post(
    "/{booking_id}/cancellation/approve",
    response_model=BookingRead,
    dependencies=[Depends(require_admin_or_above)],
)
async def approve_cancellation(
    booking_id: uuid.UUID,
    current_user: CurrentUser,
    converter: ConverterDep,
    bookings: BookingService = Depends(get_booking_service),
    cancellations: CancellationService = Depends(get_cancellation_service),
) -> BookingRead:
    booking = await bookings.get_visible(booking_id, current_user)
    if booking is None:
        raise not_found("Booking not found")
    cancelled = await cancellations.approve(booking, current_user)
    return _to_read(cancelled, current_user, converter)


@router.post(
    "/{booking_id}/cancellation/reject",
    response_model=CancellationRequestRead,
    dependencies=[Depends(require_admin_or_above)],
)
async def reject_cancellation(
    booking_id: uuid.UUID,
    current_user: CurrentUser,
    bookings: BookingService = Depends(get_booking_service),
    cancellations: CancellationService = Depends(get_cancellation_service),
) -> CancellationRequestRead:
    booking = await bookings.get_visible(booking_id, current_user)
    if booking is None:
        raise not_found("Booking not found")
    request = await cancellations.reject(booking, current_user)
    return CancellationRequestRead.model_validate(request)
