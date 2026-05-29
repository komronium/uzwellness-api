import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, not_found
from app.api.rate_limits import booking_rate_limit
from app.core.database import get_db
from app.core.pagination import Pagination
from app.models.booking import Booking
from app.models.user import User, UserRole
from app.schemas.booking import (
    BookingCreate,
    BookingCustomerRead,
    BookingList,
    BookingRead,
    InvoiceRead,
)
from app.services.booking_invoice import build_invoice
from app.services.booking_service import BookingService, get_booking_service

router = APIRouter(prefix="/bookings", tags=["Bookings"])

_ADMIN_ROLES = {UserRole.ADMIN, UserRole.SUPER_ADMIN}


def _to_read(booking: Booking, viewer: User) -> BookingRead:
    data = BookingRead.model_validate(booking)
    if viewer.role in _ADMIN_ROLES and booking.user is not None:
        data.customer = BookingCustomerRead.model_validate(booking.user)
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
    bookings: BookingService = Depends(get_booking_service),
) -> BookingRead:
    booking = await bookings.create(payload, current_user)
    return _to_read(booking, current_user)


@router.get("", response_model=BookingList)
async def list_bookings(
    current_user: CurrentUser,
    page: Pagination,
    is_b2b: bool | None = Query(default=None),
    agent_id: uuid.UUID | None = Query(default=None),
    bookings: BookingService = Depends(get_booking_service),
) -> BookingList:
    items, total = await bookings.list_for_user(
        current_user,
        limit=page.limit,
        offset=page.offset,
        is_b2b=is_b2b,
        agent_id=agent_id,
    )
    return BookingList(
        items=[_to_read(b, current_user) for b in items],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/{booking_id}", response_model=BookingRead)
async def get_booking(
    booking_id: uuid.UUID,
    current_user: CurrentUser,
    bookings: BookingService = Depends(get_booking_service),
) -> BookingRead:
    booking = await bookings.get_visible(booking_id, current_user)
    if booking is None:
        raise not_found("Booking not found")
    return _to_read(booking, current_user)


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


@router.patch("/{booking_id}/cancel", response_model=BookingRead)
async def cancel_booking(
    booking_id: uuid.UUID,
    current_user: CurrentUser,
    bookings: BookingService = Depends(get_booking_service),
) -> BookingRead:
    booking = await bookings.get_visible(booking_id, current_user)
    if booking is None:
        raise not_found("Booking not found")
    cancelled = await bookings.cancel(booking, current_user)
    return _to_read(cancelled, current_user)
