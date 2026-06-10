from __future__ import annotations

import asyncio
import time

from fastapi import HTTPException, Request, status

from app.core.config import settings
from app.core.redis_client import get_redis
from app.models.user import User

_memory_counts: dict[str, tuple[int, float]] = {}
_memory_lock = asyncio.Lock()
_CLEANUP_INTERVAL = 300
_last_cleanup: float = 0.0


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded and _is_trusted_proxy(request):
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _is_trusted_proxy(request: Request) -> bool:
    if not settings.TRUSTED_PROXY_IPS:
        return False
    peer = request.client.host if request.client else None
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
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests, please try again later",
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
            return await _incr_memory(key, self.window_seconds)
        try:
            count = await client.incr(key)
            if count == 1:
                await client.expire(key, self.window_seconds)
            return int(count)
        except Exception:
            return await _incr_memory(key, self.window_seconds)


__all__ = ["RateLimiter"]
