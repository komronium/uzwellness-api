from fastapi import Request

from app.api.deps import OptionalUser
from app.core.rate_limit import RateLimiter

login_rate_limit = RateLimiter(prefix="login", limit=10, window_seconds=600, scope="ip")
register_rate_limit = RateLimiter(
    prefix="register", limit=5, window_seconds=3600, scope="ip"
)
newsletter_rate_limit = RateLimiter(
    prefix="newsletter", limit=5, window_seconds=3600, scope="ip"
)
_booking_rate_limit = RateLimiter(
    prefix="booking", limit=20, window_seconds=86400, scope="user"
)
# Every request-code call sends an email, so an unlimited one is a way to bill
# us for someone else's inbox. Five in an hour covers a guest who mistypes the
# code and asks for a fresh one a few times.
_cancellation_code_rate_limit = RateLimiter(
    prefix="cancel-code", limit=5, window_seconds=3600, scope="user"
)
# A payment intent is a database row per call and nothing rate-limits the
# button behind it.
_payment_rate_limit = RateLimiter(
    prefix="payment", limit=20, window_seconds=3600, scope="user"
)
# Uzum's callbacks are unauthenticated by design (the spec signs nothing), and
# each one makes us call Uzum back. nginx should still allowlist Uzum's
# addresses; this is the floor underneath that.
checkout_callback_rate_limit = RateLimiter(
    prefix="checkout-callback", limit=600, window_seconds=60, scope="ip"
)


async def booking_rate_limit(request: Request, user: OptionalUser = None) -> None:
    await _booking_rate_limit.check(request, user)


async def cancellation_code_rate_limit(
    request: Request, user: OptionalUser = None
) -> None:
    await _cancellation_code_rate_limit.check(request, user)


async def payment_rate_limit(request: Request, user: OptionalUser = None) -> None:
    await _payment_rate_limit.check(request, user)
