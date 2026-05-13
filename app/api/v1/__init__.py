from fastapi import APIRouter

from app.api.v1.routers import (
    amenities,
    auth,
    bookings,
    exchange_rates,
    extra_beds,
    health,
    programs,
    reviews,
    rooms,
    sanatoriums,
    users,
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
api_router.include_router(extra_beds.router)
api_router.include_router(reviews.router)
