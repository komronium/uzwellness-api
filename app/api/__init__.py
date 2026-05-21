from fastapi import APIRouter

from app.api.routers import (
    admin,
    amenities,
    auth,
    availability,
    b2b,
    bookings,
    exchange_rates,
    extra_beds,
    health,
    packages,
    payments,
    programs,
    reviews,
    rooms,
    sanatoriums,
    transfers,
    users,
    visa_requests,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(sanatoriums.router)
api_router.include_router(rooms.router)
api_router.include_router(exchange_rates.router)
api_router.include_router(bookings.router)
api_router.include_router(amenities.router)
api_router.include_router(programs.router)
api_router.include_router(packages.router)
api_router.include_router(extra_beds.router)
api_router.include_router(reviews.router)
api_router.include_router(availability.router)
api_router.include_router(payments.router)
api_router.include_router(admin.router)
api_router.include_router(b2b.router)
api_router.include_router(visa_requests.router)
api_router.include_router(transfers.router)
