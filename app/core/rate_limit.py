from __future__ import annotations

import asyncio
import logging
import time

from fastapi import HTTPException, Request, status

from app.core.config import settings
from app.core.redis_client import close_redis, get_redis
from app.models.user import User

logger = logging.getLogger(__name__)

_memory_counts: dict[str, tuple[int, float]] = {}
_memory_lock = asyncio.Lock()
_CLEANUP_INTERVAL = 300
_last_cleanup: float = 0.0

# Redis is down/unreachable: rate limits fall back to a per-worker-process
# in-memory counter, which is a real degradation (each uvicorn worker gets
# its own count, so the effective limit multiplies by worker count). Log it,
# but rate-limited — this path can be hit on every single request during an
# outage, and a log line per request would flood the logs exactly when they
# are most needed.
_FALLBACK_LOG_INTERVAL = 30
_last_fallback_log: float = 0.0


def _client_ip(request: Request) -> str:
    """The guest's own address, or a constant when we genuinely cannot tell.

    In production the app listens on a unix socket, so there *is* no peer
    address: ``request.client`` is ``None`` and ``TRUSTED_PROXY_IPS`` can never
    match. Nothing but nginx can open that socket, so its forwarded headers are
    the only signal there is, and they are believed. Over TCP (dev, or a
    port-bound deploy) the peer is real, so they are believed only when the
    peer is a proxy we listed — otherwise any caller could pick its own
    rate-limit bucket.
    """

    peer = request.client.host if request.client else None
    if peer is None or _is_trusted_proxy(peer):
        return _forwarded_ip(request) or peer or "unknown"
    return peer


def _forwarded_ip(request: Request) -> str | None:
    """The address our proxies recorded, ignoring anything the client claimed.

    ``X-Real-IP`` is set by nginx to ``$remote_addr``: one address, overwritten
    rather than appended, so it cannot carry a client's invention and is used
    as-is. ``X-Forwarded-For`` is appended to by each hop, so the client's own
    guesses sit on the left and our proxies on the right. Walking it from the
    right past every address we recognise as a proxy lands on the first hop we
    did not add — the real caller.
    """

    real_ip = (request.headers.get("x-real-ip") or "").strip()
    if real_ip:
        return real_ip[:64]
    forwarded = request.headers.get("x-forwarded-for")
    if not forwarded:
        return None
    hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
    for hop in reversed(hops):
        if not _is_trusted_proxy(hop):
            return hop[:64]
    # Every hop is one of our own proxies, which should not happen; the
    # outermost of them is still a better bucket than lumping the world
    # together under "unknown".
    return hops[0][:64] if hops else None


def _is_trusted_proxy(peer: str) -> bool:
    if not settings.TRUSTED_PROXY_IPS:
        return False
    return peer in settings.TRUSTED_PROXY_IPS


async def _incr_memory(key: str, window: int) -> int:
    global _last_cleanup
    async with _memory_lock:
        now = time.monotonic()
        if now - _last_cleanup > _CLEANUP_INTERVAL:
            expired = [k for k, (_, exp) in _memory_counts.items() if exp < now]
            for k in expired:
                del _memory_counts[k]
            _last_cleanup = now

        count, expires_at = _memory_counts.get(key, (0, 0.0))
        if expires_at < now:
            count, expires_at = 0, now + window
        count += 1
        _memory_counts[key] = (count, expires_at)
        return count


class RateLimiter:
    def __init__(
        self,
        *,
        prefix: str,
        limit: int,
        window_seconds: int,
        scope: str = "ip",
    ) -> None:
        self.prefix = prefix
        self.limit = limit
        self.window_seconds = window_seconds
        self.scope = scope

    async def __call__(self, request: Request) -> None:
        await self.check(request)

    async def check(self, request: Request, user: User | None = None) -> None:
        if not settings.RATE_LIMIT_ENABLED:
            return

        identity = self._identity(request, user)
        if identity is None:
            return

        key = f"rl:{self.prefix}:{identity}"
        count = await self._increment(key)
        if count > self.limit:
            # Retry-After is what a well-behaved client waits on; the
            # sentence is what the guest reads when it does not.
            wait = self.window_seconds
            phrase = f"{wait // 60} minute(s)" if wait >= 60 else f"{wait} second(s)"
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(f"Too many attempts. Please wait {phrase} and try again."),
                headers={"Retry-After": str(wait)},
            )

    def _identity(self, request: Request, user: User | None) -> str | None:
        if self.scope == "user":
            if user is None:
                return None
            return f"u:{user.id}"
        return f"ip:{_client_ip(request)}"

    async def _increment(self, key: str) -> int:
        client = await get_redis()
        if client is None:
            _log_redis_fallback("no client")
            return await _incr_memory(key, self.window_seconds)
        try:
            count = await client.incr(key)
            if count == 1:
                await client.expire(key, self.window_seconds)
            return int(count)
        except Exception as exc:
            _log_redis_fallback(exc)
            # The cached client just failed mid-life (as opposed to never
            # having connected) — drop it so the next request re-establishes
            # and ping-validates a fresh connection instead of retrying the
            # same broken client forever.
            await close_redis()
            return await _incr_memory(key, self.window_seconds)


def _log_redis_fallback(reason: object) -> None:
    global _last_fallback_log
    now = time.monotonic()
    if now - _last_fallback_log > _FALLBACK_LOG_INTERVAL:
        logger.warning(
            "Rate limiter falling back to in-process memory (Redis: %s). "
            "Limits are per-worker-process until Redis recovers.",
            reason,
        )
        _last_fallback_log = now


__all__ = ["RateLimiter"]
