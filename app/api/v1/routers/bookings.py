import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import CurrentUser
from app.schemas.booking import BookingCreate, BookingList, BookingRead
from app.services.booking_service import BookingService, get_booking_service

router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.post("", response_model=BookingRead, status_code=status.HTTP_201_CREATED)
async def create_booking(
    payload: BookingCreate,
    current_user: CurrentUser,
    bookings: BookingService = Depends(get_booking_service),
) -> BookingRead:
    booking = await bookings.create(payload, current_user)
    return BookingRead.model_validate(booking)


@router.get("", response_model=BookingList)
async def list_bookings(
    current_user: CurrentUser,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    bookings: BookingService = Depends(get_booking_service),
) -> BookingList:
    items, total = await bookings.list_for_user(current_user, limit=limit, offset=offset)
    return BookingList(
        items=[BookingRead.model_validate(b) for b in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{booking_id}", response_model=BookingRead)
async def get_booking(
    booking_id: uuid.UUID,
    current_user: CurrentUser,
    bookings: BookingService = Depends(get_booking_service),
) -> BookingRead:
    booking = await bookings.get_visible(booking_id, current_user)
    if booking is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found"
        )
    return BookingRead.model_validate(booking)


@router.patch("/{booking_id}/cancel", response_model=BookingRead)
async def cancel_booking(
    booking_id: uuid.UUID,
    current_user: CurrentUser,
    bookings: BookingService = Depends(get_booking_service),
) -> BookingRead:
    booking = await bookings.get_visible(booking_id, current_user)
    if booking is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found"
        )
    cancelled = await bookings.cancel(booking, current_user)
    return BookingRead.model_validate(cancelled)
