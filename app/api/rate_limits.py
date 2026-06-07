from fastapi import Request

from app.api.deps import OptionalUser
from app.core.rate_limit import RateLimiter

login_rate_limit = RateLimiter(prefix="login", limit=10, window_seconds=600, scope="ip")
register_rate_limit = RateLimiter(
    prefix="register", limit=5, window_seconds=3600, scope="ip"
)
_booking_rate_limit = RateLimiter(
    prefix="booking", limit=20, window_seconds=86400, scope="user"
)


async def booking_rate_limit(request: Request, user: OptionalUser = None) -> None:
    await _booking_rate_limit.check(request, user)
